import asyncio
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import flet as ft
from sqlalchemy import event
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.automatic_backup import AutomaticDriveBackup
from trail_mania.database import get_database_path, initialize_database
from trail_mania.database_events import subscribe_database_changes
from trail_mania.drive_backup import DriveBackupResult, DriveBackupRetentionError, GoogleDriveConnectionRequired
from trail_mania.session_repository import create_session, delete_session, update_session


class CommittedChangesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory.name}))
        initialize_database()
        self.states = []

        class Listener:
            def database_changed(listener, database):
                # A separate connection sees only committed data.
                with closing(sqlite3.connect(database)) as db:
                    self.states.append(db.execute("SELECT date FROM sessions ORDER BY id").fetchall())

        self.listener = Listener()
        subscribe_database_changes(self.listener)

    def test_add_edit_and_delete_notify_only_after_commit(self):
        identifier = create_session(date(2026, 11, 4), "Muscu jambes")
        update_session(identifier, date(2026, 11, 5), "Muscu jambes", None)
        delete_session(identifier)
        self.assertEqual(self.states, [[("2026-11-04",)], [("2026-11-05",)], []])
        delete_session(identifier)
        self.assertEqual(len(self.states), 3)

    def test_failed_commit_does_not_notify_for_any_write(self):
        identifier = create_session(date(2026, 11, 4), "Muscu jambes")
        self.states.clear()

        def fail_commit(_session):
            raise RuntimeError("commit failed")

        event.listen(DatabaseSession, "before_commit", fail_commit)
        self.addCleanup(event.remove, DatabaseSession, "before_commit", fail_commit)
        for operation in (
            lambda: create_session(date(2026, 11, 5), "Muscu jambes"),
            lambda: update_session(identifier, date(2026, 11, 5), "Muscu jambes", None),
            lambda: delete_session(identifier),
        ):
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                operation()
        self.assertEqual(self.states, [])
        with closing(sqlite3.connect(get_database_path())) as db:
            self.assertEqual(db.execute("SELECT date FROM sessions").fetchall(), [("2026-11-04",)])

    def test_listener_error_does_not_report_successful_write_as_failed(self):
        failing = Mock()
        failing.database_changed.side_effect = RuntimeError("scheduler closed")
        subscribe_database_changes(failing)
        with self.assertLogs("trail_mania.database_events", level="WARNING"):
            identifier = create_session(date(2026, 11, 4), "Muscu jambes")
        self.assertIsInstance(identifier, int)
        self.assertEqual(self.states, [[("2026-11-04",)]])


class AutomaticBackupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory.name}))
        self.page = Mock()
        self.auth = Mock()
        self.controller = AutomaticDriveBackup(self.page, self.auth)
        self.backup = self.enterContext(patch(
            "trail_mania.automatic_backup.backup_database_to_drive", new_callable=AsyncMock,
        ))
        self.prune = self.enterContext(patch(
            "trail_mania.automatic_backup.prune_drive_backups", new_callable=AsyncMock,
        ))

    async def run_scheduled(self):
        await self.page.run_task.call_args.args[0]()

    def test_without_drive_connection_writes_do_not_schedule_uploads(self):
        self.controller.database_changed(get_database_path().resolve())
        self.page.run_task.assert_not_called()

    async def test_connecting_backs_up_existing_local_data_immediately(self):
        self.controller.connected()
        self.page.run_task.assert_called_once()
        await self.run_scheduled()
        self.backup.assert_awaited_once_with(self.auth)

    async def test_restored_connection_backs_up_each_write_but_not_on_enable(self):
        self.controller.enable()
        self.page.run_task.assert_not_called()
        self.controller.database_changed(get_database_path().resolve())
        await self.run_scheduled()
        self.backup.assert_awaited_once_with(self.auth)
        self.controller.database_changed(Path("another-database.db").resolve())
        self.page.run_task.assert_called_once()

    async def test_rapid_changes_are_all_backed_up_serially(self):
        self.controller.enable()
        started = asyncio.Event()
        release = asyncio.Event()

        async def block_backup(_auth):
            started.set()
            await release.wait()

        self.backup.side_effect = block_backup
        for _ in range(2):
            self.controller.database_changed(get_database_path().resolve())
        self.page.run_task.assert_called_once()
        tasks = [asyncio.create_task(call.args[0]()) for call in self.page.run_task.call_args_list]
        await started.wait()
        self.assertEqual(self.backup.await_count, 1)
        release.set()
        await asyncio.gather(*tasks)
        self.assertEqual(self.backup.await_count, 2)

    async def test_failure_retries_without_another_database_write(self):
        self.controller.enable()
        self.backup.side_effect = [OSError("offline"), None]
        self.controller.database_changed(get_database_path().resolve())
        with patch.object(self.controller, "_wait_to_retry", new_callable=AsyncMock) as wait:
            await self.run_scheduled()
        wait.assert_awaited_once_with(15)
        message = self.page.show_dialog.call_args.args[0].content.value
        self.assertIn("restent enregistrées", message)
        self.assertEqual(self.backup.await_count, 2)
        self.assertEqual(self.controller._pending, 0)

    async def test_partial_success_has_distinct_feedback(self):
        self.backup.side_effect = DriveBackupRetentionError(DriveBackupResult("id", "backup.db"))
        self.controller.connected()
        with patch.object(self.controller, "_wait_to_retry", new_callable=AsyncMock):
            await self.run_scheduled()
        message = self.page.show_dialog.call_args.args[0].content.value
        self.assertIn("Sauvegarde envoyée", message)
        self.backup.assert_awaited_once()
        self.prune.assert_awaited_once_with(self.auth)
        self.assertFalse(self.controller._cleanup_pending)

    async def test_backoff_increases_and_is_capped_without_repeated_error_messages(self):
        self.backup.side_effect = [OSError("offline")] * 7 + [None]
        self.controller.connected()
        with patch.object(self.controller, "_wait_to_retry", new_callable=AsyncMock) as wait:
            await self.run_scheduled()
        self.assertEqual([call.args[0] for call in wait.await_args_list], [15, 30, 60, 120, 240, 300, 300])
        self.page.show_dialog.assert_called_once()

    async def test_restart_resumes_persisted_uploads(self):
        self.controller.connected()
        state = self.controller._state_path
        self.assertTrue(state.is_file())
        restarted = AutomaticDriveBackup(self.page, self.auth)
        restarted.enable()
        await self.run_scheduled()
        self.backup.assert_awaited_once_with(self.auth)
        self.assertEqual(restarted._pending, 0)
        again = AutomaticDriveBackup(self.page, self.auth)
        self.assertEqual(again._pending, 0)

    async def test_restart_resumes_cleanup_without_uploading_again(self):
        self.controller._cleanup_pending = True
        self.controller._save_state()
        restarted = AutomaticDriveBackup(self.page, self.auth)
        restarted.enable()
        await self.run_scheduled()
        self.backup.assert_not_awaited()
        self.prune.assert_awaited_once_with(self.auth)

    async def test_network_return_wakes_a_retry_immediately(self):
        self.backup.side_effect = [OSError("offline"), None]
        self.controller.connected()
        waiting = asyncio.Event()
        original_wait = self.controller._wait_to_retry

        async def wait(delay):
            waiting.set()
            await original_wait(delay)

        with patch.object(self.controller, "_wait_to_retry", side_effect=wait):
            task = asyncio.create_task(self.page.run_task.call_args.args[0]())
            await asyncio.wait_for(waiting.wait(), timeout=2)
            self.controller.connectivity_changed(SimpleNamespace(connectivity=[ft.ConnectivityType.WIFI]))
            await self.page.run_task.call_args.args[0]()
            await asyncio.wait_for(task, timeout=2)
        self.assertEqual(self.backup.await_count, 2)

    async def test_foreground_event_resumes_pending_work_without_new_upload_request(self):
        self.controller.connected()
        self.controller.lifecycle_changed(SimpleNamespace(state=ft.AppLifecycleState.RESUME))
        await self.page.run_task.call_args.args[0]()
        self.assertEqual(self.controller._pending, 1)
        self.assertTrue(self.controller._wake.is_set())

    def test_disconnection_event_does_not_schedule_an_attempt(self):
        self.controller.connected()
        self.page.run_task.reset_mock()
        self.controller.connectivity_changed(SimpleNamespace(connectivity=[ft.ConnectivityType.NONE]))
        self.page.run_task.assert_not_called()

    async def test_authentication_error_waits_for_reconnection_and_preserves_pending_work(self):
        self.backup.side_effect = GoogleDriveConnectionRequired("revoked")
        self.controller.connected()
        with patch.object(self.controller, "_wait_to_retry", new_callable=AsyncMock) as wait:
            await self.run_scheduled()
        wait.assert_not_awaited()
        self.assertEqual(self.controller._pending, 1)
        self.assertFalse(self.controller._worker_active)

    async def test_shutdown_during_retry_preserves_pending_work(self):
        self.backup.side_effect = OSError("offline")
        self.controller.connected()
        with patch.object(self.controller, "_wait_to_retry", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.run_scheduled()
        restarted = AutomaticDriveBackup(self.page, self.auth)
        self.assertEqual(restarted._pending, 1)
        self.assertFalse(self.controller._worker_active)

    def test_closed_controller_does_not_overwrite_pending_state_on_later_writes(self):
        self.controller.connected()
        worker_future = self.page.run_task.return_value
        self.controller.close()
        worker_future.cancel.assert_called_once()
        self.controller.database_changed(get_database_path().resolve())
        self.controller.enable()
        self.assertEqual(self.controller._pending, 1)
        self.assertFalse(self.controller._enabled)
        self.assertEqual(AutomaticDriveBackup(self.page, self.auth)._pending, 1)

    async def test_changes_during_an_upload_are_not_lost(self):
        self.controller.connected()
        started, release = asyncio.Event(), asyncio.Event()

        async def block_once(_auth):
            started.set()
            await release.wait()

        self.backup.side_effect = block_once
        task = asyncio.create_task(self.page.run_task.call_args.args[0]())
        await asyncio.wait_for(started.wait(), timeout=2)
        self.controller.database_changed(get_database_path().resolve())
        release.set()
        await asyncio.wait_for(task, timeout=2)
        self.assertEqual(self.backup.await_count, 2)
        self.assertEqual(self.controller._pending, 0)

    def test_closed_page_scheduler_does_not_break_writes(self):
        self.page.run_task.side_effect = RuntimeError("closed")
        self.controller.enable()
        with self.assertLogs("trail_mania.automatic_backup", level="WARNING"):
            self.controller.database_changed(get_database_path().resolve())
