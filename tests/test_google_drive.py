import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import flet as ft

from trail_mania.app import create_app
from trail_mania.google_drive import get_google_client_id
from trail_mania.views.google_drive_view import GoogleDriveView


CLIENT_ID = "test-client.apps.googleusercontent.com"


class DriveConfigurationTests(unittest.TestCase):
    def test_packaged_mobile_assets_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "google_drive.json"
            config.write_text(json.dumps({"web_client_id": CLIENT_ID}), encoding="utf-8")
            with patch.dict(os.environ, {
                "FLET_ASSETS_DIR": directory,
                "TRAIL_MANIA_GOOGLE_WEB_CLIENT_ID": "",
            }):
                self.assertEqual(get_google_client_id(), CLIENT_ID)
                config.write_text("invalid JSON", encoding="utf-8")
                self.assertEqual(get_google_client_id(), "")


class DriveStartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory.name}))

    async def start(self, result=None, error=None):
        page = Mock(platform=ft.PagePlatform.ANDROID, web=False, controls=[])
        page.add.side_effect = lambda control: page.controls.append(control)
        auth = Mock(restore=AsyncMock(return_value=result, side_effect=error))
        with (
            patch("trail_mania.app.initialize_database"),
            patch("trail_mania.app.GoogleDriveAuth", return_value=auth),
            patch("trail_mania.app._show_main_views") as show_main,
            patch.object(GoogleDriveView, "update"),
        ):
            await create_app(page)
        return page, auth, show_main

    async def test_saved_connection_opens_main_views(self):
        page, auth, show_main = await self.start({"status": "connected"})
        auth.restore.assert_awaited_once()
        show_main.assert_called_once_with(page)
        controller = page.session.store.set.call_args.args[1]
        self.assertTrue(controller._enabled)
        page.run_task.assert_not_called()

    async def test_successful_new_connection_schedules_initial_backup(self):
        page, auth, _ = await self.start({"status": "disconnected"})
        auth.connect = AsyncMock(return_value={"status": "connected"})
        view = page.controls[0].content
        with (
            patch("trail_mania.app._show_main_views"),
            patch("trail_mania.views.google_drive_view.get_google_client_id", return_value=CLIENT_ID),
            patch.object(GoogleDriveView, "update"),
            patch("trail_mania.automatic_backup.backup_database_to_drive", new_callable=AsyncMock) as backup,
        ):
            await view._connect(None)
            page.run_task.assert_called_once()
            await page.run_task.call_args.args[0]()
            backup.assert_awaited_once_with(auth)

    async def test_missing_connection_shows_connection_view_without_navigation(self):
        page, _, show_main = await self.start({"status": "disconnected"})
        show_main.assert_not_called()
        self.assertIsNone(page.navigation_bar)
        self.assertIsInstance(page.controls[0].content, GoogleDriveView)

    async def test_unreadable_storage_keeps_app_usable(self):
        page, _, show_main = await self.start(error=RuntimeError("storage unavailable"))
        show_main.assert_not_called()
        view = page.controls[0].content
        self.assertIn("pas pu être lue", view._message.value)
        self.assertFalse(view._skip_button.disabled)

    async def test_desktop_does_not_wait_for_unavailable_native_extension(self):
        page = Mock(platform=ft.PagePlatform.WINDOWS, web=False, controls=[])
        auth = Mock(restore=AsyncMock())
        with (
            patch("trail_mania.app.initialize_database"),
            patch("trail_mania.app.GoogleDriveAuth", return_value=auth),
            patch.object(GoogleDriveView, "update"),
        ):
            await create_app(page)
        auth.restore.assert_not_awaited()
        self.assertTrue(page.add.call_args.args[0].content._connect_button.disabled)


class DriveConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = Mock(connect=AsyncMock())
        self.on_continue = Mock()
        self.on_connected = Mock()
        self.view = GoogleDriveView(self.auth, self.on_continue, on_connected=self.on_connected)
        self.enterContext(patch.object(GoogleDriveView, "update"))
        self.enterContext(patch(
            "trail_mania.views.google_drive_view.get_google_client_id", return_value=CLIENT_ID,
        ))

    async def test_success_continues_after_native_persistence(self):
        self.auth.connect.return_value = {"status": "connected", "email": "runner@example.com"}
        await self.view._connect(None)
        self.auth.connect.assert_awaited_once_with(CLIENT_ID)
        self.on_continue.assert_called_once_with()
        self.on_connected.assert_called_once_with()

    async def test_cancel_denied_consent_and_persistence_errors_allow_retry(self):
        for status in ("canceled", "authorization_required", "error", "clientConfigurationError"):
            with self.subTest(status=status):
                self.auth.connect.return_value = {"status": status}
                await self.view._connect(None)
                self.on_continue.assert_not_called()
                self.on_connected.assert_not_called()
                self.assertFalse(self.view._connect_button.disabled)
                self.assertFalse(self.view._skip_button.disabled)
                self.assertTrue(self.view._message.value)

    async def test_bridge_failure_does_not_unlock_app(self):
        self.auth.connect.side_effect = TimeoutError()
        await self.view._connect(None)
        self.on_continue.assert_not_called()
        self.assertFalse(self.view._busy)

    async def test_no_client_id_does_not_start_oauth(self):
        with patch("trail_mania.views.google_drive_view.get_google_client_id", return_value=""):
            await self.view._connect(None)
        self.auth.connect.assert_not_awaited()
        self.on_continue.assert_not_called()

    async def test_duplicate_click_and_skip_are_ignored_while_connecting(self):
        self.view._busy = True
        await self.view._connect(None)
        self.view._skip_button.on_click(SimpleNamespace())
        self.auth.connect.assert_not_awaited()
        self.on_continue.assert_not_called()

    def test_skip_does_not_create_or_save_credentials(self):
        self.view._skip_button.on_click(SimpleNamespace())
        self.on_continue.assert_called_once_with()
        self.auth.connect.assert_not_called()
        self.on_connected.assert_not_called()
