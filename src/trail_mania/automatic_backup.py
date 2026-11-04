"""Persist backup requests and retry them when Drive becomes available again."""

import asyncio
import json
import logging
import threading
from pathlib import Path

import flet as ft
from trail_mania_drive import GoogleDriveAuth

from trail_mania.database import get_database_path
from trail_mania.database_events import subscribe_database_changes, unsubscribe_database_changes
from trail_mania.drive_backup import (
    DriveBackupRetentionError, GoogleDriveConnectionRequired,
    backup_database_to_drive, prune_drive_backups,
)

_logger = logging.getLogger(__name__)
_INITIAL_RETRY_DELAY = 15
_MAX_RETRY_DELAY = 300


class AutomaticDriveBackup:
    """Run one worker per page and retain unfinished work across app restarts."""

    def __init__(self, page: ft.Page, auth: GoogleDriveAuth):
        self._page = page
        self._auth = auth
        self._database = get_database_path().resolve()
        self._state_path = self._database.with_name("drive_backup_state.json")
        self._lock = threading.RLock()
        self._enabled = False
        self._closed = False
        self._worker_active = False
        self._worker_future = None
        self._wake = asyncio.Event()
        self._pending, self._cleanup_pending = self._load_state()
        subscribe_database_changes(self)

    def _load_state(self) -> tuple[int, bool]:
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
            pending, cleanup = state["pending"], state["cleanup_pending"]
            if type(pending) is not int or pending < 0 or type(cleanup) is not bool:
                raise ValueError()
            return pending, cleanup
        except FileNotFoundError:
            return 0, False
        except (OSError, ValueError, KeyError, TypeError):
            _logger.warning("Could not read pending Drive backup state")
            return 1, False

    def _save_state(self) -> None:
        """Replace atomically while holding the state lock; store no credentials."""
        temporary = self._state_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps({
                "pending": self._pending, "cleanup_pending": self._cleanup_pending,
            }), encoding="utf-8")
            temporary.replace(self._state_path)
        except OSError:
            _logger.warning("Could not persist pending Drive backup state")

    def enable(self) -> None:
        """Resume unfinished work after restoring a saved Google session."""
        with self._lock:
            if self._closed:
                return
            self._enabled = True
            self._ensure_worker()

    def connected(self) -> None:
        """Upload existing local data after consent, including pending changes."""
        with self._lock:
            if self._closed:
                return
            if not self._pending:
                self._pending = 1
                self._save_state()
            self.enable()

    def database_changed(self, database: Path) -> None:
        if database == self._database:
            with self._lock:
                if self._closed:
                    return
                self._pending += 1
                self._save_state()
                self._ensure_worker()

    def _ensure_worker(self) -> None:
        """Called with the lock held, including from synchronous write handlers."""
        if self._enabled and not self._worker_active and (self._pending or self._cleanup_pending):
            self._worker_active = True
            try:
                self._worker_future = self._page.run_task(self._backup)
            except Exception:
                self._worker_active = False
                _logger.warning("Could not schedule Google Drive backup")

    def retry_pending(self) -> None:
        """Wake retries from a connectivity or foreground event, without adding work."""
        with self._lock:
            if self._enabled and (self._pending or self._cleanup_pending):
                try:
                    self._page.run_task(self._resume)
                except Exception:
                    _logger.warning("Could not resume Google Drive backup")

    async def _resume(self) -> None:
        self._wake.set()
        with self._lock:
            self._ensure_worker()

    def connectivity_changed(self, event: ft.ConnectivityChangeEvent) -> None:
        # A network interface is a reason to retry, not proof of Internet access.
        if any(network != ft.ConnectivityType.NONE for network in event.connectivity):
            self.retry_pending()

    def lifecycle_changed(self, event: ft.AppLifecycleStateChangeEvent) -> None:
        if event.state == ft.AppLifecycleState.RESUME:
            self.retry_pending()

    def close(self, _event=None) -> None:
        """Stop this page's retry loop; unfinished work remains on disk."""
        with self._lock:
            self._closed = True
            self._enabled = False
            unsubscribe_database_changes(self)
            if self._worker_future is not None:
                self._worker_future.cancel()

    async def _wait_to_retry(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _backup(self) -> None:
        delay = _INITIAL_RETRY_DELAY
        warned = False
        released = False
        try:
            while True:
                with self._lock:
                    upload = self._pending > 0
                    if not self._enabled or not (upload or self._cleanup_pending):
                        self._worker_active = False
                        released = True
                        return
                self._wake.clear()
                try:
                    if upload:
                        await backup_database_to_drive(self._auth)
                    else:
                        await prune_drive_backups(self._auth)
                except DriveBackupRetentionError:
                    with self._lock:
                        self._pending -= 1
                        self._cleanup_pending = True
                        self._save_state()
                    if not warned:
                        self._show_error(
                            "Sauvegarde envoyée sur Google Drive. Le nettoyage des anciennes sauvegardes "
                            "sera retenté automatiquement."
                        )
                        warned = True
                except GoogleDriveConnectionRequired:
                    self._show_error("Reconnecte ton compte Google Drive pour reprendre les sauvegardes en attente.")
                    return
                except Exception:
                    if not warned:
                        self._show_error(
                            "La sauvegarde Google Drive est en attente. Tes données restent enregistrées "
                            "sur cet appareil. Un nouvel essai sera fait automatiquement."
                        )
                        warned = True
                else:
                    with self._lock:
                        if upload:
                            self._pending -= 1
                        self._cleanup_pending = False
                        self._save_state()
                    delay = _INITIAL_RETRY_DELAY
                    warned = False
                    continue
                await self._wait_to_retry(delay)
                delay = min(delay * 2, _MAX_RETRY_DELAY)
        finally:
            if not released:
                with self._lock:
                    self._worker_active = False

    def _show_error(self, message: str) -> None:
        try:
            self._page.show_dialog(ft.SnackBar(ft.Text(message)))
        except Exception:
            _logger.warning("Could not display Google Drive backup feedback")
