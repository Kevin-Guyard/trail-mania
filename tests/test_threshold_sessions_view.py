import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import flet as ft

from trail_mania.app import change_page
from trail_mania.database import initialize_database
from trail_mania.session_records import IntervalSession
from trail_mania.session_repository import (
    create_session,
    get_calendar_sessions_by_date,
    get_sessions,
)
from trail_mania.session_types import (
    Movement,
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
)
from trail_mania.views.sessions import SessionsView


class ThresholdRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        initialize_database()

    @staticmethod
    def save(day, **overrides):
        values = dict(
            field_type="Route", slope_type="Sans pente", dynamic_type=None,
            duration_ON=Decimal("12.5"), duration_OFF=None,
            velocity_ON_1=13.37, mean_HR_ON_1=151, max_HR_ON_1=166,
            RPE=Decimal("6.5"), comment="Continu",
            **{f"Z{i}": timedelta(seconds=i * 10) for i in range(1, 6)},
        )
        values.update(overrides)
        create_session(day, SessionType.THRESHOLD, values)

    def test_query_preserves_repetitions_nulls_and_date_order(self):
        self.assertEqual(get_sessions(SessionType.THRESHOLD), [])
        self.save(date(2026, 12, 31))
        repeated = {
            "duration_OFF": Decimal("2.5"), "velocity_ON_2": 14.1, "velocity_ON_3": 14.2,
            "velocity_OFF_1": 8.0, "velocity_OFF_2": 8.2, "mean_HR_ON_2": 155,
            "mean_HR_ON_3": 158, "max_HR_ON_2": 170, "max_HR_ON_3": 175,
        }
        self.save(date(2027, 1, 1), **repeated, comment="Première")
        self.save(date(2027, 1, 1), **repeated, comment="Dernière")
        create_session(date(2027, 1, 2), SessionType.LEG_STRENGTH)
        last, first, continuous = get_sessions(SessionType.THRESHOLD)
        self.assertEqual([last.comment, first.comment, continuous.comment],
                         ["Dernière", "Première", "Continu"])
        self.assertEqual(continuous.session_format, SessionFormat.CONTINUOUS)
        self.assertEqual(continuous.velocity_on, (13.37, None, None))
        self.assertEqual(continuous.velocity_off, (None, None))
        self.assertEqual(continuous.mean_hr_on, (151, None, None))
        self.assertIsNone(continuous.duration_off)
        self.assertEqual(last.session_format, SessionFormat.THREE_REPETITIONS)
        self.assertEqual(last.duration_on, Decimal("12.5"))
        self.assertEqual(last.duration_off, Decimal("2.5"))
        self.assertEqual(last.velocity_on, (13.37, 14.1, 14.2))
        self.assertEqual(last.velocity_off, (8.0, 8.2))
        self.assertEqual(last.mean_hr_on, (151, 155, 158))
        self.assertEqual(last.max_hr_on, (166, 170, 175))
        self.assertEqual(last.z5, timedelta(seconds=50))

    def test_zero_speed_is_a_populated_repetition(self):
        session = IntervalSession(date.today(), "Route", "Sans pente", None,
                                   velocity_on=(12.0, 0.0, None))
        self.assertEqual(session.session_format, SessionFormat.THREE_REPETITIONS)

    def test_sparse_repetitions_have_the_same_format_in_the_calendar_and_list(self):
        for day, measurements in (
            (date(2026, 11, 10), {"velocity_OFF_1": 0.0}),
            (date(2026, 11, 11), {"velocity_ON_3": 0.0}),
        ):
            with self.subTest(measurements=measurements):
                self.save(day, **measurements)
                record = get_sessions(SessionType.THRESHOLD)[0]
                self.assertEqual(record.session_format, SessionFormat.THREE_REPETITIONS)
                calendar_record, = get_calendar_sessions_by_date(day, day)[day]
                self.assertEqual(calendar_record.description, "Route - Sans pente - x3")


class IntervalSessionsViewTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(ft.Control, "update", autospec=True))
        self.sessions = [
            IntervalSession(
                date(2026, 11, 10), "Route", "Sans pente", None,
                duration_on=Decimal("20.0"), velocity_on=(13.37, None, None),
                mean_hr_on=(150, None, None), max_hr_on=(165, None, None),
            ),
            IntervalSession(
                date(2026, 11, 9), "Route", "Sans pente", None,
                duration_on=Decimal("8.5"), duration_off=Decimal("2.0"),
                velocity_on=(13.0, 13.5, 14.0), velocity_off=(8.0, 8.5),
                mean_hr_on=(150, 155, 160), max_hr_on=(165, 170, 175),
                z1=timedelta(seconds=30), z2=timedelta(seconds=70),
            ),
            IntervalSession(date(2026, 11, 8), "Tapis", "Avec pente", "Marche"),
        ]
        self.reader = self.enterContext(patch(
            "trail_mania.views.sessions._session_list.get_sessions", return_value=self.sessions,
        ))
        self.view = SessionsView()
        self.view._open_session(SessionType.THRESHOLD)
        self.panel = self.view._session_list
        self.filters = self.panel.filters
        self.table = self.panel.table

    def choose(self, group, value, checked=True):
        box = getattr(self.filters, f"{group}_choices")[value]
        box.value = checked
        box.on_change(ft.Event("change", box))

    def rows(self):
        headers = [column.label.value for column in self.table._table.columns]
        return [dict(zip(headers, [
            cell.content.content.value if isinstance(cell.content.content, ft.Text)
            else getattr(cell.content.content, "semantics_label", None)
            for cell in row.cells
        ], strict=True)) for row in self.table._table.rows]

    def select_location(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)

    def test_format_is_required_and_both_formats_can_be_selected(self):
        self.assertEqual(self.rows(), [])
        self.assertEqual([box.label for box in self.filters.format_choices.values()],
                         ["x 1", "x 3"])
        self.select_location()
        self.assertEqual(self.rows(), [])
        self.choose("format", SessionFormat.CONTINUOUS)
        self.assertEqual([row["Date"] for row in self.rows()], ["10/11/2026"])
        self.choose("format", SessionFormat.THREE_REPETITIONS)
        self.assertEqual(len(self.rows()), 2)
        self.choose("format", SessionFormat.CONTINUOUS, False)
        self.assertEqual([row["Date"] for row in self.rows()], ["09/11/2026"])
        self.choose("format", SessionFormat.THREE_REPETITIONS, False)
        self.assertEqual(self.rows(), [])
        self.reader.assert_called_once()

    def test_continuous_uses_repetition_one_and_preserves_nulls(self):
        self.select_location()
        self.choose("format", SessionFormat.CONTINUOUS)
        row, = self.rows()
        self.assertNotIn("Dist", row)
        self.assertNotIn("Vit", row)
        self.assertEqual(row["Dur ON"], "20,0 min")
        self.assertEqual(row["Dur OFF"], "—")
        self.assertEqual(row["Vit ON 1"], "13,4 km/h")
        self.assertEqual(row["FC moy ON 1"], "150 bpm")
        self.assertEqual(row["FC max ON 1"], "165 bpm")
        for column in ("Vit OFF 1", "Vit ON 2", "Vit OFF 2", "Vit ON 3",
                       "FC moy ON 2", "FC max ON 2", "FC moy ON 3", "FC max ON 3"):
            self.assertEqual(row[column], "—")
        self.assertEqual(self.sessions[0].velocity_on[0], 13.37)

    def test_three_repetitions_have_individual_speeds_and_heart_rates(self):
        self.select_location()
        self.choose("format", SessionFormat.THREE_REPETITIONS)
        row, = self.rows()
        self.assertEqual(row["Dur ON"], "8,5 min")
        self.assertEqual(row["Dur OFF"], "2,0 min")
        self.assertEqual([row[f"Vit ON {i}"] for i in range(1, 4)],
                         ["13,0 km/h", "13,5 km/h", "14,0 km/h"])
        self.assertEqual([row[f"Vit OFF {i}"] for i in range(1, 3)], ["8,0 km/h", "8,5 km/h"])
        self.assertEqual([row[f"FC max ON {i}"] for i in range(1, 4)], ["165 bpm", "170 bpm", "175 bpm"])
        self.assertEqual([row[f"% Z{i}"] for i in range(1, 6)], ["30 %", "70 %", "0 %", "0 %", "0 %"])

    def test_format_does_not_bypass_location_or_movement_filters(self):
        self.choose("format", SessionFormat.CONTINUOUS)
        self.assertEqual(self.rows(), [])
        self.choose("terrain", Terrain.TREADMILL)
        self.assertEqual(self.rows(), [])
        self.choose("slope", Slope.HILLY)
        self.assertEqual(self.rows(), [])
        self.choose("movement", Movement.WALK)
        self.assertEqual(len(self.rows()), 1)
        self.choose("movement", Movement.WALK, False)
        self.assertEqual(self.rows(), [])

    def test_tab_refresh_preserves_format_and_back_discards_subview(self):
        self.select_location()
        self.choose("format", SessionFormat.THREE_REPETITIONS)
        nav = ft.NavigationBar(selected_index=0)
        change_page(ft.Event("change", nav), Mock(), [self.view], ft.Container())
        self.assertTrue(self.filters.format_choices[SessionFormat.THREE_REPETITIONS].value)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.reader.call_count, 2)
        self.view._back_to_choices()
        self.assertIsNone(self.view._session_list)
        self.assertIs(self.view.content, self.view._session_choices)


if __name__ == "__main__":
    unittest.main()
