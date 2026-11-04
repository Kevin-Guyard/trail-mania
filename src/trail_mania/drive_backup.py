"""Create consistent SQLite snapshots and keep the newest 20 copies in Drive."""

import asyncio
import json
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from trail_mania_drive import GoogleDriveAuth

from trail_mania.database import get_database_path
from trail_mania.google_drive import get_google_client_id

_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
_BACKUP_MARKER = {"trail_mania_backup": "sqlite-v1"}
_BACKUP_LOCK = threading.Lock()
_KEEP_BACKUPS = 20


class DriveBackupError(Exception):
    """Backup could not be confirmed; no retention cleanup was started."""


class GoogleDriveConnectionRequired(DriveBackupError):
    """Google Drive needs to be configured or authorized again."""


@dataclass(frozen=True)
class DriveBackupResult:
    """Confirmed uploaded file and the old backups successfully removed."""

    file_id: str
    filename: str
    deleted_file_ids: tuple[str, ...] = ()


class DriveBackupRetentionError(DriveBackupError):
    """Upload succeeded, but the retention cleanup did not finish.

    ``result`` identifies the uploaded copy and any completed deletions. Callers
    should report partial success rather than automatically uploading it again.
    """

    def __init__(self, result: DriveBackupResult):
        super().__init__("Sauvegarde envoyée, mais le nettoyage des anciennes sauvegardes a échoué.")
        self.result = result


async def backup_database_to_drive(auth: GoogleDriveAuth) -> DriveBackupResult:
    """Snapshot the application database, upload it, then retain 20 backups.

    Use the native authorization service stored in ``page.session.store`` under
    ``drive_auth``. The filename uses local time and three millisecond digits:
    ``trail_mania_YYYY_MM_DD_HH_MM_SS_mmm.db``. The live database is not renamed.
    Files are stored in the private Drive app-data folder. Only this function's
    marked backups are counted and deleted, after a confirmed upload. SQLite and
    HTTP work run in a worker thread; overlapping calls in this process serialize.

    Raises GoogleDriveConnectionRequired before upload when authorization is
    unavailable, DriveBackupError for Drive failures, and DriveBackupRetentionError
    if upload succeeded but cleanup failed. Local filesystem and SQLite failures
    propagate without deleting any remote backup.
    """
    token = await _get_access_token(auth)
    return await asyncio.to_thread(_backup_and_prune, get_database_path(), token)


async def prune_drive_backups(auth: GoogleDriveAuth) -> tuple[str, ...]:
    """Retry retention independently, without uploading another database copy."""
    token = await _get_access_token(auth)
    return await asyncio.to_thread(_prune_with_lock, token)


async def _get_access_token(auth: GoogleDriveAuth) -> str:
    client_id = get_google_client_id()
    if not client_id:
        raise GoogleDriveConnectionRequired("La connexion Google Drive n’est pas configurée.")
    credentials = await auth.access_token(client_id)
    token = credentials.get("access_token")
    if credentials.get("status") != "connected" or not isinstance(token, str) or not token:
        if credentials.get("status") in ("error", "unknownError", "interrupted", "uiUnavailable"):
            raise DriveBackupError("La connexion à Google Drive est temporairement indisponible.")
        raise GoogleDriveConnectionRequired("Reconnecte ton compte Google Drive pour sauvegarder.")
    return token


def _request(
    method: str, url: str, token: str, *, body: bytes | BinaryIO | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict, dict]:
    """Make a bounded HTTPS request without exposing tokens in error messages."""
    request = Request(
        url, data=body, method=method,
        headers={"Authorization": f"Bearer {token}", **(headers or {})},
    )
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read()
            data = json.loads(raw) if raw else {}
            if not isinstance(data, dict):
                raise ValueError("Unexpected Drive response")
            return data, dict(response.headers.items())
    except HTTPError as error:
        status = error.code
        error.close()
        if status == 401:
            raise GoogleDriveConnectionRequired("Reconnecte ton compte Google Drive pour sauvegarder (HTTP 401).") from None
        raise DriveBackupError(f"Google Drive a refusé l’opération (HTTP {status}).") from None
    except (URLError, OSError, HTTPException, ValueError):
        raise DriveBackupError("L’opération Google Drive n’a pas pu être confirmée.") from None


def _snapshot(source: Path, destination: Path) -> None:
    """Include committed WAL transactions without copying an actively written file."""
    deadline = time.monotonic() + 30

    def check_timeout(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("La base est occupée ; réessaie la sauvegarde.")

    # Read-only mode also prevents accidentally creating a missing source DB.
    with (
        closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(destination)) as snapshot,
    ):
        original.backup(snapshot, pages=256, progress=check_timeout)


def _upload(snapshot: Path, token: str) -> dict:
    metadata = {
        "name": snapshot.name, "parents": ["appDataFolder"],
        "appProperties": _BACKUP_MARKER,
    }
    size = snapshot.stat().st_size
    _, headers = _request(
        "POST", _UPLOAD_URL + "?" + urlencode({
            "uploadType": "resumable", "fields": "id,name,createdTime",
        }), token, body=json.dumps(metadata).encode("utf-8"), headers={
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/vnd.sqlite3",
            "X-Upload-Content-Length": str(size),
        },
    )
    session_url = next((value for key, value in headers.items() if key.lower() == "location"), "")
    parsed = urlparse(session_url)
    if parsed.scheme != "https" or parsed.netloc != "www.googleapis.com":
        raise DriveBackupError("Google Drive n’a pas fourni de destination d’envoi valide.")
    # Stream the snapshot, keeping memory use independent of database size.
    with snapshot.open("rb") as stream:
        uploaded, _ = _request("PUT", session_url, token, body=stream, headers={
            "Content-Type": "application/vnd.sqlite3", "Content-Length": str(size),
        })
    _validate_file(uploaded)
    return uploaded


def _validate_file(file: dict) -> None:
    if not all(isinstance(file.get(key), str) and file[key] for key in ("id", "name", "createdTime")):
        raise DriveBackupError("Les informations de sauvegarde reçues de Drive sont incomplètes.")
    try:
        timestamp = datetime.fromisoformat(file["createdTime"])
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise DriveBackupError("La date de sauvegarde reçue de Drive est invalide.") from None


def _list_backups(token: str) -> dict[str, dict]:
    """Read all pages before deleting anything; ignore other application files."""
    files = {}
    page_token = ""
    visited_pages = set()
    while True:
        params = {
            "spaces": "appDataFolder",
            "q": "trashed = false and 'appDataFolder' in parents and "
                 "appProperties has { key='trail_mania_backup' and value='sqlite-v1' }",
            "fields": "nextPageToken,incompleteSearch,files(id,name,createdTime)",
            "pageSize": 1000,
            "orderBy": "createdTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        data, _ = _request("GET", _FILES_URL + "?" + urlencode(params), token)
        if data.get("incompleteSearch") or not isinstance(data.get("files"), list):
            raise DriveBackupError("La liste des sauvegardes Google Drive est incomplète.")
        for file in data["files"]:
            if not isinstance(file, dict):
                raise DriveBackupError("La liste des sauvegardes Google Drive est invalide.")
            _validate_file(file)
            files[file["id"]] = file
        page_token = data.get("nextPageToken", "")
        if not page_token:
            return files
        if not isinstance(page_token, str) or page_token in visited_pages:
            raise DriveBackupError("La pagination des sauvegardes Google Drive est invalide.")
        visited_pages.add(page_token)


def _backup_and_prune(database: Path, token: str) -> DriveBackupResult:
    with _BACKUP_LOCK, TemporaryDirectory(prefix="trail-mania-backup-") as directory:
        now = datetime.now().astimezone()
        suffix = now.strftime("%Y_%m_%d_%H_%M_%S_") + f"{now.microsecond // 1000:03d}"
        filename = f"{database.stem}_{suffix}{database.suffix}"
        snapshot = Path(directory) / filename
        _snapshot(database, snapshot)
        uploaded = _upload(snapshot, token)
        deleted = _prune_backups(token, uploaded)
        return DriveBackupResult(uploaded["id"], filename, tuple(deleted))


def _prune_with_lock(token: str) -> tuple[str, ...]:
    with _BACKUP_LOCK:
        return _prune_backups(token)


def _prune_backups(token: str, uploaded: dict | None = None) -> tuple[str, ...]:
    deleted = []
    try:
        backups = _list_backups(token)
        # The just-uploaded copy may not be visible in the list immediately.
        if uploaded is not None:
            backups[uploaded["id"]] = uploaded
        oldest_first = sorted(backups.values(), key=lambda file: (
            datetime.fromisoformat(file["createdTime"]), file["id"],
        ))
        excess = max(0, len(oldest_first) - _KEEP_BACKUPS)
        for file in oldest_first[:excess]:
            _request("DELETE", _FILES_URL + "/" + quote(file["id"], safe=""), token)
            deleted.append(file["id"])
    except DriveBackupError:
        if uploaded is None:
            raise
        raise DriveBackupRetentionError(DriveBackupResult(
            uploaded["id"], uploaded["name"], tuple(deleted),
        )) from None
    return tuple(deleted)
