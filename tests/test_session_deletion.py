import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, PropertyMock, patch

import flet as ft
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.database import create_database_engine, initialize_database
from trail_mania.models import Session
from trail_mania.session_repository import (
    DETAIL_MODELS, create_session, delete_session, get_calendar_sessions_by_date,
    get_detail_fields, get_sessions, get_strength_sessions,
)
from trail_mania.session_types import SessionType, Slope, Terrain
from trail_mania.views.calendar.calendar_view import CalendarView
from trail_mania.views.sessions import SessionsView
from trail_mania.views.sessions import session_detail_view
from trail_mania.views.sessions.session_detail_view import SessionDetailView


def walk(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", []):
        yield from walk(child)


class SessionDeletionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        self.enterContext(patch.object(ft.Control, "update"))
        self.page = Mock()
        self.enterContext(patch.object(SessionDetailView, "page", new_callable=PropertyMock, return_value=self.page))
        initialize_database()
        self.day = date.today()

    def save(self, family):
        values = None
        if family.has_details:
            values = {}
            for name, spec in get_detail_fields(family).items():
                if name == "field_type":
                    value = "Route"
                elif name == "slope_type":
                    value = "Sans pente"
                elif name == "comment":
                    value = "Même séance"
                elif not spec.required:
                    value = None
                elif spec.value_type is timedelta:
                    value = timedelta(minutes=1)
                elif spec.value_type is Decimal:
                    value = Decimal("5.0")
                elif spec.value_type is float:
                    value = 12.0
                else:
                    value = 150
                values[name] = value
        return create_session(self.day, family, values)

    def ids(self):
        engine = create_database_engine()
        try:
            with DatabaseSession(engine) as db:
                return set(db.scalars(select(Session.id)))
        finally:
            engine.dispose()

    def record(self, family, session_id):
        records = get_sessions(family) if family.has_details else get_strength_sessions()
        return next(record for record in records if record.session_id == session_id)

    def open_list_detail(self, family):
        view = SessionsView()
        view._open_session(family)
        panel = view._session_list
        if family.has_details:
            panel.filters.terrain_choices[Terrain.ROAD].value = True
            panel.filters.slope_choices[Slope.FLAT].value = True
            for checkbox in panel.filters.format_choices.values():
                checkbox.value = True
            panel._on_filter_change()
            rows = panel.table._table.rows
        else:
            rows = panel.table.rows
        rows[0].on_select_change(ft.Event("select_change", rows[0]))
        return view, panel

    def popup(self, detail):
        button = detail.controls[0].controls[-1]
        self.assertIsInstance(button, ft.IconButton)
        self.assertEqual(button.icon, ft.Icons.DELETE_OUTLINE)
        self.assertEqual(button.tooltip, "Supprimer")
        self.assertFalse(button.disabled)
        button.on_click(ft.Event("click", button))
        dialog = self.page.show_dialog.call_args.args[0]
        self.assertEqual(dialog.content.value, "Cette action est définitive")
        self.assertEqual([button.content for button in dialog.actions], ["Supprimer", "Annuler"])
        return dialog

    def test_identity_and_cascade_for_every_family_and_duplicate_session(self):
        for family in SessionType:
            with self.subTest(family=family):
                selected, survivor = self.save(family), self.save(family)
                self.assertEqual(self.record(family, selected).session_id, selected)
                calendar = get_calendar_sessions_by_date(self.day, self.day)[self.day]
                self.assertIn(selected, [session.record.session_id for session in calendar])
                delete_session(selected)
                self.assertNotIn(selected, self.ids())
                self.assertIn(survivor, self.ids())
                if family.has_details:
                    engine = create_database_engine()
                    try:
                        with DatabaseSession(engine) as db:
                            remaining = set(db.scalars(select(DETAIL_MODELS[family].session_id)))
                            self.assertNotIn(selected, remaining)
                            self.assertIn(survivor, remaining)
                    finally:
                        engine.dispose()
                delete_session(selected)
                self.assertIn(survivor, self.ids())

    def test_cancel_leaves_detail_and_database_unchanged_for_every_family(self):
        for family in SessionType:
            with self.subTest(family=family):
                self.save(family)
                view, panel = self.open_list_detail(family)
                detail = view.content
                before = self.ids()
                dialog = self.popup(detail)
                with patch.object(session_detail_view, "delete_session") as writer:
                    dialog.actions[1].on_click(None)
                    dialog.actions[0].on_click(None)  # Ignore an event from a cancelled dialog.
                    writer.assert_not_called()
                self.assertEqual(self.ids(), before)
                self.assertIs(view.content, detail)
                self.assertIs(view._session_list, panel)
                self.page.pop_dialog.assert_called()

    def test_confirm_rebuilds_list_preserving_filters_and_blocks_double_delete(self):
        for family in SessionType:
            with self.subTest(family=family):
                self.save(family)
                self.save(family)
                view, panel = self.open_list_detail(family)
                detail = view.content
                selected = detail.session.session_id
                selection = None
                if family.has_details:
                    # Simulate a list opened while scrolled well below its filters.
                    panel.table._scroll_offset = 1000
                    panel.table._filters_height = 178
                    panel.table._position_header(update=False)
                    # Hidden movement choices must survive too.
                    panel.filters.movement_choices[next(iter(panel.filters.movement_choices))].value = True
                    selection = panel.filters.selection
                original = view._list_content
                dialog = self.popup(detail)
                with patch.object(session_detail_view, "delete_session", wraps=delete_session) as writer:
                    dialog.actions[0].on_click(None)
                    dialog.actions[0].on_click(None)
                    writer.assert_called_once_with(selected)
                self.assertNotIn(selected, self.ids())
                self.assertIsNot(view.content, original)
                self.assertIsNot(view._session_list, panel)
                self.assertIs(view.content, view._list_content)
                panel = view._session_list
                rows = panel.table._table.rows if family.has_details else panel.table.rows
                self.assertEqual(len(rows), 1)
                if family.has_details:
                    self.assertEqual(panel.filters.selection, selection)
                    self.assertEqual(panel.table._scroll_offset, 0)
                    self.assertEqual(panel.table._sticky_header.top, 0)
                    self.assertTrue(panel.filters.terrain_choices[Terrain.ROAD].value)
                    self.assertTrue(panel.filters.slope_choices[Slope.FLAT].value)
                    self.assertTrue(all(c.value for c in panel.filters.format_choices.values()))

    def test_confirm_returns_to_original_calendar_mode_and_period_for_every_family(self):
        for family in SessionType:
            for mode in ("month", "week"):
                with self.subTest(family=family, mode=mode):
                    selected = self.save(family)
                    self.save(family)
                    view = CalendarView()
                    selector = next(c for c in walk(view) if isinstance(c, ft.SegmentedButton))
                    selector.selected = [mode]
                    selector.on_change(ft.Event("change", selector))
                    period = view.selected_month, view.selected_week
                    records = get_calendar_sessions_by_date(self.day, self.day)[self.day]
                    index = next(i for i, session in enumerate(records) if session.record.session_id == selected)
                    grid = view._pager._pages[1].content
                    cell = next(c for c in walk(grid) if isinstance(c, ft.Container)
                                and c.tooltip == self.day.strftime("%d/%m/%Y"))
                    band = cell.content.controls[0].content.controls[index * 2]
                    band.on_click(ft.Event("click", band))
                    self.assertEqual(view.content.session.session_id, selected)
                    dialog = self.popup(view.content)
                    dialog.actions[0].on_click(None)
                    self.assertIs(view.content, view._calendar_content)
                    self.assertEqual(selector.selected, [mode])
                    self.assertEqual((view.selected_month, view.selected_week), period)
                    self.assertNotIn(selected, self.ids())
                    refreshed = get_calendar_sessions_by_date(self.day, self.day)[self.day]
                    self.assertEqual(len(refreshed), len(records) - 1)

    def test_failure_keeps_confirmation_and_allows_retry_without_navigation(self):
        selected = self.save(SessionType.EASY_RUN)
        view, _ = self.open_list_detail(SessionType.EASY_RUN)
        detail = view.content
        dialog = self.popup(detail)
        with patch.object(session_detail_view, "delete_session", side_effect=SQLAlchemyError("failure")):
            dialog.actions[0].on_click(None)
        self.assertIs(view.content, detail)
        self.assertIn(selected, self.ids())
        self.assertIs(detail._delete_dialog, dialog)
        self.assertIn("Impossible", dialog.content.value)
        self.assertFalse(detail._deleting)
        dialog.actions[0].on_click(None)
        self.assertNotIn(selected, self.ids())
        self.assertIs(view.content, view._list_content)

    def test_cancelled_confirmation_cannot_delete_through_a_new_dialog(self):
        selected = self.save(SessionType.EASY_RUN)
        view, _ = self.open_list_detail(SessionType.EASY_RUN)
        detail = view.content
        previous = self.popup(detail)
        previous.actions[1].on_click(None)
        current = self.popup(detail)
        with patch.object(session_detail_view, "delete_session", wraps=delete_session) as writer:
            previous.actions[0].on_click(None)
            previous.actions[1].on_click(None)
            previous.on_dismiss(None)
            writer.assert_not_called()
            self.assertIs(detail._delete_dialog, current)
            self.assertIn(selected, self.ids())
            current.actions[0].on_click(None)
            writer.assert_called_once_with(selected)
        self.assertNotIn(selected, self.ids())

    def test_dismissed_confirmation_can_be_reopened_and_does_not_delete(self):
        selected = self.save(SessionType.EASY_RUN)
        view, _ = self.open_list_detail(SessionType.EASY_RUN)
        detail = view.content
        previous = self.popup(detail)
        previous.on_dismiss(None)
        previous.actions[0].on_click(None)
        self.assertIn(selected, self.ids())
        current = self.popup(detail)
        self.assertIsNot(current, previous)
        current.actions[1].on_click(None)
        self.assertIs(view.content, detail)

    def test_old_detail_events_cannot_delete_or_navigate_after_opening_editor(self):
        self.save(SessionType.EASY_RUN)
        view, _ = self.open_list_detail(SessionType.EASY_RUN)
        detail = view.content
        detail.controls[-1].controls[1].on_click(None)
        editor = view.content
        self.page.show_dialog.reset_mock()
        with patch.object(session_detail_view, "delete_session") as writer:
            detail.controls[0].controls[-1].on_click(None)
            detail.controls[0].controls[0].on_click(None)
            detail.controls[-1].controls[1].on_click(None)
            self.assertIs(view.content, editor)
            self.page.show_dialog.assert_not_called()
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
