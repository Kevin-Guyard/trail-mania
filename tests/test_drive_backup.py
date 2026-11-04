import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from trail_mania.drive_backup import (
    DriveBackupError, DriveBackupRetentionError, GoogleDriveConnectionRequired,
    backup_database_to_drive, prune_drive_backups,
)


def remote_file(identifier, offset):
    return {
        "id": identifier, "name": f"trail_mania_{identifier}.db",
        "createdTime": (datetime(2026, 1, 1, tzinfo=timezone.utc)
                        + timedelta(seconds=offset)).isoformat(),
    }


class DriveBackupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / "trail_mania.db"
        self.connection = sqlite3.connect(self.database)
        self.addCleanup(self.connection.close)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE sessions (comment TEXT)")
        self.connection.execute("INSERT INTO sessions VALUES ('Séance sauvegardée')")
        self.connection.commit()
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": str(self.root)}))
        self.client_id = self.enterContext(patch(
            "trail_mania.drive_backup.get_google_client_id", return_value="web-client",
        ))
        self.auth = Mock(access_token=AsyncMock(return_value={
            "status": "connected", "access_token": "secret-token",
        }))
        self.pages = [{"files": []}]
        self.uploaded = remote_file("uploaded", 1000)
        self.requests = []
        self.deletions = []
        self.upload_error = None
        self.list_error = None
        self.delete_error_id = None
        self.snapshot_path = None
        self.urlopen = self.enterContext(patch(
            "trail_mania.drive_backup.urlopen", side_effect=self.handle_request,
        ))

    def handle_request(self, request, timeout):
        self.requests.append(request)
        self.assertEqual(timeout, 60)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        method = request.get_method()
        if method == "POST":
            metadata = json.loads(request.data)
            self.assertEqual(metadata["parents"], ["appDataFolder"])
            self.assertEqual(metadata["appProperties"], {"trail_mania_backup": "sqlite-v1"})
            self.assertRegex(metadata["name"], r"^trail_mania_\d{4}(?:_\d{2}){5}_\d{3}\.db$")
            self.uploaded["name"] = metadata["name"]
            data, headers = {}, {"Location": "https://www.googleapis.com/upload/session"}
        elif method == "PUT":
            if self.upload_error:
                raise self.upload_error
            content = request.data.read()
            self.assertEqual(len(content), int(request.get_header("Content-length")))
            self.snapshot_path = Path(request.data.name)
            # Confirm the upload is a usable SQLite snapshot, including WAL data.
            restored = self.root / "restored.db"
            restored.write_bytes(content)
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("SELECT comment FROM sessions").fetchall(),
                                 [("Séance sauvegardée",)])
            data, headers = self.uploaded, {}
        elif method == "GET":
            if self.list_error:
                raise self.list_error
            params = parse_qs(urlparse(request.full_url).query)
            self.assertEqual(params["spaces"], ["appDataFolder"])
            self.assertIn("'appDataFolder' in parents", params["q"][0])
            self.assertIn("appProperties has", params["q"][0])
            self.assertIn("trail_mania_backup", params["q"][0])
            index = int(params.get("pageToken", ["0"])[0])
            data, headers = self.pages[index], {}
        elif method == "DELETE":
            identifier = request.full_url.rsplit("/", 1)[-1]
            if identifier == self.delete_error_id:
                raise URLError("offline")
            self.deletions.append(identifier)
            data, headers = None, {}
        else:
            self.fail(f"Unexpected method {method}")
        response = io.BytesIO(json.dumps(data).encode() if data is not None else b"")
        response.headers = headers
        return response

    async def test_uploads_dated_snapshot_without_renaming_live_database(self):
        result = await backup_database_to_drive(self.auth)
        self.assertEqual(result.file_id, "uploaded")
        self.assertEqual(result.filename, self.uploaded["name"])
        self.assertEqual(result.deleted_file_ids, ())
        self.assertEqual([r.get_method() for r in self.requests], ["POST", "PUT", "GET"])
        self.assertTrue(self.database.is_file())
        self.assertFalse(self.snapshot_path.exists())
        self.auth.access_token.assert_awaited_once_with("web-client")

    async def test_twentieth_backup_does_not_delete_anything(self):
        self.pages = [{"files": [remote_file(f"old-{i}", i) for i in range(19)]}]
        await backup_database_to_drive(self.auth)
        self.assertEqual(self.deletions, [])

    async def test_twenty_first_backup_deletes_oldest(self):
        self.pages = [{"files": [remote_file(f"old-{i}", i) for i in reversed(range(20))]}]
        result = await backup_database_to_drive(self.auth)
        self.assertEqual(result.deleted_file_ids, ("old-0",))

    async def test_all_pages_are_read_before_removing_every_excess_backup(self):
        self.pages = [
            {"files": [remote_file(f"old-{i}", i) for i in range(12, 24)], "nextPageToken": "1"},
            {"files": [remote_file(f"old-{i}", i) for i in range(12)] + [self.uploaded]},
        ]
        result = await backup_database_to_drive(self.auth)
        self.assertEqual(result.deleted_file_ids, tuple(f"old-{i}" for i in range(5)))
        methods = [r.get_method() for r in self.requests]
        self.assertEqual(methods[:4], ["POST", "PUT", "GET", "GET"])

    async def test_upload_failure_never_lists_or_deletes_backups(self):
        self.upload_error = URLError("offline")
        with self.assertRaises(DriveBackupError):
            await backup_database_to_drive(self.auth)
        self.assertEqual([r.get_method() for r in self.requests], ["POST", "PUT"])
        self.assertEqual(self.deletions, [])

    async def test_incomplete_listing_reports_uploaded_copy_without_deleting(self):
        self.pages = [{"files": [remote_file(f"old-{i}", i) for i in range(30)],
                       "incompleteSearch": True}]
        with self.assertRaises(DriveBackupRetentionError) as caught:
            await backup_database_to_drive(self.auth)
        self.assertEqual(caught.exception.result.file_id, "uploaded")
        self.assertEqual(self.deletions, [])
        self.assertFalse(self.snapshot_path.exists())

    async def test_missing_second_page_prevents_all_deletions(self):
        self.pages = [
            {"files": [remote_file(f"old-{i}", i) for i in range(25)], "nextPageToken": "1"},
            {"unexpected": []},
        ]
        with self.assertRaises(DriveBackupRetentionError):
            await backup_database_to_drive(self.auth)
        self.assertEqual(self.deletions, [])

    async def test_partial_cleanup_reports_uploaded_copy_and_completed_deletions(self):
        self.pages = [{"files": [remote_file(f"old-{i}", i) for i in range(22)]}]
        self.delete_error_id = "old-1"
        with self.assertRaises(DriveBackupRetentionError) as caught:
            await backup_database_to_drive(self.auth)
        self.assertEqual(caught.exception.result.deleted_file_ids, ("old-0",))
        self.assertEqual(caught.exception.result.file_id, "uploaded")
        self.assertEqual(self.deletions, ["old-0"])

    async def test_invalid_remote_dates_prevent_all_deletions(self):
        self.pages = [{"files": [{**remote_file("invalid", 0), "createdTime": "invalid"}]}]
        with self.assertRaises(DriveBackupRetentionError):
            await backup_database_to_drive(self.auth)
        self.assertEqual(self.deletions, [])

    async def test_failed_authentication_does_not_read_or_upload_database(self):
        self.auth.access_token.return_value = {"status": "authorization_required"}
        with self.assertRaises(GoogleDriveConnectionRequired):
            await backup_database_to_drive(self.auth)
        self.urlopen.assert_not_called()

    async def test_missing_configuration_does_not_start_backup(self):
        self.client_id.return_value = ""
        with self.assertRaises(GoogleDriveConnectionRequired):
            await backup_database_to_drive(self.auth)
        self.auth.access_token.assert_not_awaited()
        self.urlopen.assert_not_called()

    async def test_missing_database_is_not_created_and_no_upload_occurs(self):
        missing = self.root / "missing.db"
        with patch("trail_mania.drive_backup.get_database_path", return_value=missing):
            with self.assertRaises(sqlite3.OperationalError):
                await backup_database_to_drive(self.auth)
        self.assertFalse(missing.exists())
        self.urlopen.assert_not_called()

    async def test_http_errors_do_not_expose_tokens_or_response_bodies(self):
        self.upload_error = HTTPError("https://www.googleapis.com", 401, "secret-token", {},
                                      io.BytesIO(b"secret response"))
        with self.assertRaises(DriveBackupError) as caught:
            await backup_database_to_drive(self.auth)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(self.deletions, [])

    async def test_retry_cleanup_does_not_upload_another_database(self):
        self.pages = [{"files": [remote_file(f"old-{i}", i) for i in range(23)]}]
        deleted = await prune_drive_backups(self.auth)
        self.assertEqual(deleted, ("old-0", "old-1", "old-2"))
        self.assertEqual([r.get_method() for r in self.requests], ["GET", "DELETE", "DELETE", "DELETE"])

    async def test_temporary_native_auth_failure_is_retryable(self):
        self.auth.access_token.return_value = {"status": "unknownError"}
        with self.assertRaises(DriveBackupError) as caught:
            await backup_database_to_drive(self.auth)
        self.assertNotIsInstance(caught.exception, GoogleDriveConnectionRequired)
        self.urlopen.assert_not_called()
