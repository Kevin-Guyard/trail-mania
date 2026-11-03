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
from trail_mania.session_repository import create_session, get_sessions
from trail_mania.session_types import (
    Movement,
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
)
from trail_mania.views.sessions import SessionsView


def summary(repetitions, **overrides):
    values = {
        "date": date(2026, 11, repetitions), "terrain": "Route", "slope": "Sans pente", "movement": None,
        "session_type": SessionType.VO2MAX, "duration_on": Decimal("3.5"), "duration_off": Decimal("1.0"),
        "velocity_on": tuple(14.0 + i if i < repetitions else None for i in range(6)),
        "velocity_off": tuple(8.0 + i if i < repetitions - 1 else None for i in range(5)),
        "mean_hr_on": tuple(150 + i if i < repetitions else None for i in range(6)),
        "max_hr_on": tuple(170 + i if i < repetitions else None for i in range(6)),
        "z1": timedelta(seconds=30), "z2": timedelta(seconds=70), "rpe": Decimal("8.5"),
        "comment": f"VO2max {repetitions}",
    }
    values.update(overrides)
    return IntervalSession(**values)


class VO2maxRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        initialize_database()

    @staticmethod
    def save(repetitions, day, comment):
        item = summary(repetitions)
        values = dict(
            field_type=item.terrain, slope_type=item.slope,
            duration_ON=item.duration_on, duration_OFF=item.duration_off,
            RPE=item.rpe, comment=comment,
            **{f"Z{i}": getattr(item, f"z{i}") for i in range(1, 6)},
        )
        for i in range(1, 7):
            values[f"velocity_ON_{i}"] = item.velocity_on[i - 1]
            values[f"mean_HR_ON_{i}"] = item.mean_hr_on[i - 1]
            values[f"max_HR_ON_{i}"] = item.max_hr_on[i - 1]
            if i < 6:
                values[f"velocity_OFF_{i}"] = item.velocity_off[i - 1]
        create_session(day, SessionType.VO2MAX, values)

    def test_all_formats_round_trip_in_date_order_with_null_repetitions_preserved(self):
        self.assertEqual(get_sessions(SessionType.VO2MAX), [])
        self.save(4, date(2026, 12, 31), "4 répétitions")
        self.save(5, date(2027, 1, 1), "5 répétitions")
        self.save(6, date(2027, 1, 1), "6 répétitions")
        self.save(6, date(2027, 1, 1), "Doublon conservé")
        create_session(date(2027, 1, 2), SessionType.LEG_STRENGTH)
        rows = get_sessions(SessionType.VO2MAX)
        self.assertEqual([item.comment for item in rows],
                         ["Doublon conservé", "6 répétitions", "5 répétitions", "4 répétitions"])
        self.assertEqual(get_sessions(SessionType.THRESHOLD), [])
        for item, count in zip(rows, (6, 6, 5, 4), strict=True):
            expected = summary(count)
            self.assertEqual(item.session_type, SessionType.VO2MAX)
            self.assertEqual(item.session_format.repetitions, count)
            self.assertEqual(item.velocity_on, expected.velocity_on)
            self.assertEqual(item.velocity_off, expected.velocity_off)
            self.assertEqual(item.mean_hr_on, expected.mean_hr_on)
            self.assertEqual(item.max_hr_on, expected.max_hr_on)
            self.assertEqual(item.duration_on, Decimal("3.5"))
            self.assertEqual(item.z2, timedelta(seconds=70))

    def test_zero_speed_does_not_hide_the_fifth_or_sixth_repetition(self):
        for count in (5, 6):
            item = summary(count, velocity_on=(15.0,) * (count - 1) + (0.0,) + (None,) * (6 - count))
            self.assertEqual(item.session_format.repetitions, count)


class VO2maxSessionsViewTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(ft.Control, "update", autospec=True))
        self.reader = self.enterContext(patch(
            "trail_mania.views.sessions._session_list.get_sessions",
            return_value=[summary(6), summary(5), summary(4)],
        ))
        self.view = SessionsView()
        self.view._open_session(SessionType.VO2MAX)
        self.panel = self.view._session_list
        self.filters = self.panel.filters
        self.table = self.panel.table

    def choose(self, group, value, checked=True):
        box = getattr(self.filters, f"{group}_choices")[value]
        box.value = checked
        box.on_change(ft.Event("change", box))

    def rows(self):
        labels = [column.label.value for column in self.table._table.columns]
        return [dict(zip(labels, [
            cell.content.content.value if isinstance(cell.content.content, ft.Text)
            else getattr(cell.content.content, "semantics_label", None)
            for cell in row.cells
        ], strict=True)) for row in self.table._table.rows]

    def location(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)

    def test_required_format_filter_accepts_multiple_formats_and_preserves_date_order(self):
        self.assertEqual([box.label for box in self.filters.format_choices.values()],
                         ["4 répétitions", "5 répétitions", "6 répétitions"])
        self.assertEqual(self.rows(), [])
        self.location()
        self.assertEqual(self.rows(), [])
        self.choose("format", SessionFormat.FOUR_REPETITIONS)
        self.assertEqual([row["Format"] for row in self.rows()], ["x4"])
        self.choose("format", SessionFormat.SIX_REPETITIONS)
        self.assertEqual([row["Format"] for row in self.rows()], ["x6", "x4"])
        self.choose("format", SessionFormat.FIVE_REPETITIONS)
        self.assertEqual([row["Format"] for row in self.rows()], ["x6", "x5", "x4"])
        self.choose("slope", Slope.FLAT, False)
        self.assertEqual(self.rows(), [])
        self.reader.assert_called_once()

    def test_four_five_and_six_repetitions_keep_missing_values_empty(self):
        self.location()
        for choice in self.filters.format_choices:
            self.choose("format", choice)
        for row, count in zip(self.rows(), (6, 5, 4), strict=True):
            self.assertEqual(row["Dur ON"], "3,5 min")
            self.assertEqual(row["Dur OFF"], "1,0 min")
            self.assertNotIn("Dist", row)
            self.assertNotIn("Vit OFF 6", row)
            for i in range(1, 7):
                self.assertEqual(row[f"Vit ON {i}"], f"{14 + i - 1},0 km/h" if i <= count else "—")
                self.assertEqual(row[f"FC moy ON {i}"], f"{150 + i - 1} bpm" if i <= count else "—")
                self.assertEqual(row[f"FC max ON {i}"], f"{170 + i - 1} bpm" if i <= count else "—")
                if i < 6:
                    self.assertEqual(row[f"Vit OFF {i}"], f"{8 + i - 1},0 km/h" if i < count else "—")
            self.assertEqual([row[f"% Z{i}"] for i in range(1, 6)], ["30 %", "70 %", "0 %", "0 %", "0 %"])
            self.assertEqual(row["RPE"], "8,5")

    def test_format_filter_does_not_bypass_inclined_treadmill_movement(self):
        self.reader.return_value = [summary(4, terrain="Tapis", slope="Avec pente", movement="Course")]
        self.view.refresh()
        self.choose("format", SessionFormat.FOUR_REPETITIONS)
        self.choose("terrain", Terrain.TREADMILL)
        self.choose("slope", Slope.HILLY)
        self.assertEqual(self.rows(), [])
        self.choose("movement", Movement.WALK)
        self.assertEqual(self.rows(), [])
        self.choose("movement", Movement.RUN)
        self.assertEqual(len(self.rows()), 1)

    def test_refresh_preserves_filters_and_all_columns_share_the_measured_widths(self):
        self.location()
        self.choose("format", SessionFormat.SIX_REPETITIONS)
        nav = ft.NavigationBar(selected_index=0)
        change_page(ft.Event("change", nav), Mock(), [self.view], ft.Container())
        self.assertTrue(self.filters.format_choices[SessionFormat.SIX_REPETITIONS].value)
        self.assertEqual(len(self.rows()), 1)
        labels = [column.label.value for column in self.table._table.columns]
        self.assertEqual(len(labels), 41)
        index = labels.index("Vit ON 6")
        self.table._on_column_size(ft.LayoutSizeChangeEvent(
            "size_change", self.table._column_measurements, width=75.2, height=20,
        ), index)
        self.assertEqual(self.table._table_header.columns[index].label.width, 76)
        self.assertEqual(self.table._table.rows[0].cells[index].content.width, 76)
        self.assertIs(self.table._horizontal_viewport.controls[0].controls[-1].content, self.table._table_header)
        self.view._back_to_choices()
        self.assertIsNone(self.view._session_list)


if __name__ == "__main__":
    unittest.main()
