import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import flet as ft

from trail_mania.app import _show_main_views
from trail_mania.database import initialize_database
from trail_mania.navigation import configure_system_back
from trail_mania.session_records import StrengthSession
from trail_mania.session_repository import CalendarSession
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._session_edit import SessionEditView


class SystemBackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        self.enterContext(patch.object(ft.Control, "update"))
        initialize_database()
        self.root = ft.View()
        self.page = Mock(views=[self.root], controls=self.root.controls)
        self.page.add.side_effect = self.root.controls.append
        self.confirm = self.enterContext(patch.object(ft.View, "confirm_pop", new_callable=AsyncMock))
        configure_system_back(self.page)
        _show_main_views(self.page)
        self.container = self.page.controls[0].content

    def select_tab(self, index):
        bar = self.page.navigation_bar
        bar.selected_index = index
        bar.on_change(ft.Event("change", bar))
        return self.container.content

    async def back(self):
        await self.root.on_confirm_pop(ft.Event("confirm_pop", self.root))
        self.confirm.assert_awaited_with(False)
        self.assertFalse(self.root.can_pop)
        self.assertEqual(self.page.views, [self.root])

    async def test_root_tabs_ignore_back_including_calendar_period_arrows(self):
        for index in range(4):
            with self.subTest(tab=index):
                view = self.select_tab(index)
                content = view.content
                await self.back()
                self.assertIs(view.content, content)
                self.assertEqual(self.page.navigation_bar.selected_index, index)

    async def test_loading_and_connection_screens_ignore_back(self):
        for content in (ft.ProgressRing(), ft.Text("Connexion")):
            self.page.controls[:] = [ft.SafeArea(content=content)]
            await self.back()
            self.assertIs(self.page.controls[0].content, content)

    async def test_add_forms_return_to_picker_for_every_family(self):
        view = self.select_tab(3)
        picker = view.content
        for family in SessionType:
            with self.subTest(family=family):
                view._open_session(family)
                await self.back()
                self.assertIs(view.content, picker)
                self.assertIsNone(view._form)

    async def test_sessions_return_from_detail_then_list_then_ignore_back(self):
        view = self.select_tab(1)
        picker = view.content
        view._open_session(SessionType.LEG_STRENGTH)
        listing = view.content
        view._open_detail(StrengthSession(date.today()))
        await self.back()
        self.assertIs(view.content, listing)
        await self.back()
        self.assertIs(view.content, picker)
        await self.back()
        self.assertIs(view.content, picker)

    async def test_calendar_detail_returns_to_same_calendar_period(self):
        view = self.select_tab(0)
        calendar = view.content
        period = view.selected_month
        view._open_detail(CalendarSession(
            SessionType.LEG_STRENGTH, record=StrengthSession(date.today()),
        ))
        await self.back()
        self.assertIs(view.content, calendar)
        self.assertEqual(view.selected_month, period)

    async def test_only_active_tab_handles_back_and_retains_other_tabs(self):
        view = self.select_tab(3)
        view._open_session(SessionType.LEG_STRENGTH)
        form = view.content
        self.select_tab(2)
        await self.back()
        self.assertIs(view.content, form)
        self.select_tab(3)
        await self.back()
        self.assertIsNot(view.content, form)

    async def test_edit_with_changes_keeps_existing_confirmation(self):
        on_back = Mock()
        editor = SessionEditView(
            session=StrengthSession(date.today(), session_id=1),
            session_type=SessionType.LEG_STRENGTH, on_back=on_back,
        )
        self.enterContext(patch.object(SessionEditView, "page", new_callable=PropertyMock, return_value=self.page))
        self.container.content = editor
        editor.form.details_form.date_input.set_value(date.today() - timedelta(days=1))
        await self.back()
        on_back.assert_not_called()
        dialog = editor._dialog
        self.page.show_dialog.assert_called_once_with(dialog)
        await self.back()
        self.assertIs(editor._dialog, dialog)
        self.page.show_dialog.assert_called_once()
        dialog.actions[1].on_click(None)
        on_back.assert_called_once()

    async def test_hidden_and_disabled_arrows_are_ignored(self):
        action = Mock()
        button = ft.IconButton(ft.Icons.ARROW_BACK, on_click=action)
        for options in ({"visible": False}, {"disabled": True}):
            self.container.content = ft.Container(content=button, **options)
            await self.back()
        action.assert_not_called()
