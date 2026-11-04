import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import flet as ft
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack

from trail_mania.database import initialize_database
from trail_mania.session_records import StrengthSession
from trail_mania.session_repository import create_session, get_calendar_sessions_by_date, get_strength_sessions
from trail_mania.session_types import SessionType
from trail_mania.views.calendar.calendar_view import CalendarView
from trail_mania.views.sessions import SessionsView
from trail_mania.views.sessions.session_detail_view import SessionDetailView


def walk(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", []):
        yield from walk(child)


class StrengthSessionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        self.enterContext(patch.object(ft.Control, "update"))
        initialize_database()
        self.day = date.today()

    def save(self, day=None):
        create_session(day or self.day, SessionType.LEG_STRENGTH)

    def test_repository_preserves_duplicate_dates_and_calendar_record(self):
        self.assertEqual(get_strength_sessions(), [])
        self.save(self.day - timedelta(days=1))
        self.save()
        self.save()
        self.assertEqual(get_strength_sessions(), [
            StrengthSession(self.day), StrengthSession(self.day), StrengthSession(self.day - timedelta(days=1)),
        ])
        records = get_calendar_sessions_by_date(self.day, self.day)[self.day]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.record == StrengthSession(self.day) for record in records))

    def assert_detail(self, detail):
        self.assertIsInstance(detail, SessionDetailView)
        self.assertEqual(detail.controls[0].controls[1].value, "Muscu jambes")
        self.assertEqual(len(detail.controls), 4)
        row, = detail.controls[2].controls[0].rows
        self.assertEqual(row.cells[0].content.value, "Date")
        self.assertEqual(row.cells[1].content.content.value, self.day.strftime("%d/%m/%Y"))
        changes, _, _ = ObjectPatch.from_diff(None, detail, control_cls=BaseControl)
        self.assertTrue(msgpack.packb(changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl)))

    def test_list_opens_detail_and_returns_to_same_list(self):
        self.save()
        view = SessionsView()
        self.assertNotIn(SessionType.LEG_STRENGTH, view._session_choices.excluded_types)
        view._open_session(SessionType.LEG_STRENGTH)
        content = view.content
        row, = view._session_list.table.rows
        row.on_select_change(ft.Event("select_change", row))
        self.assert_detail(view.content)
        view.content.controls[0].controls[0].on_click(None)
        self.assertIs(view.content, content)
        self.save()
        view.refresh()
        self.assertEqual(len(view._session_list.table.rows), 2)
        view._back_to_choices()
        self.assertIs(view.content, view._session_choices)

    def test_empty_strength_list(self):
        view = SessionsView()
        view._open_session(SessionType.LEG_STRENGTH)
        self.assertEqual(view._session_list.table.rows, [])
        self.assertTrue(view._session_list._empty_message.visible)

    def test_both_calendars_open_strength_detail_and_return_to_original_mode(self):
        for count in (1, 2):
            self.save()
            for mode in ("month", "week"):
                with self.subTest(mode=mode, sessions=count):
                    view = CalendarView()
                    selector = next(c for c in walk(view) if isinstance(c, ft.SegmentedButton))
                    selector.selected = [mode]
                    selector.on_change(ft.Event("change", selector))
                    grid = view._pager._pages[1].content
                    cell = next(c for c in walk(grid) if isinstance(c, ft.Container)
                                and c.tooltip == self.day.strftime("%d/%m/%Y"))
                    target = cell.content.controls[0]
                    if count > 1:
                        target = target.content.controls[2]
                    target.on_click(ft.Event("click", target))
                    self.assert_detail(view.content)
                    self.assertEqual(view.content.back_tooltip, "Retour au calendrier")
                    view.content.controls[0].controls[0].on_click(None)
                    self.assertIs(view.content, view._calendar_content)
                    self.assertEqual(selector.selected, [mode])


if __name__ == "__main__":
    unittest.main()
