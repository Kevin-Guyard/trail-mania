import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import flet as ft
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack

from trail_mania.app import change_page
from trail_mania.database import initialize_database
from trail_mania.session_records import EnduranceSession, IntervalSession
from trail_mania.session_repository import create_session, get_sessions
from trail_mania.session_types import (
    SESSION_FORMATS,
    Movement,
    SessionType,
    Slope,
    Terrain,
)
from trail_mania.views.sessions import SessionsView, _session_list


class EasyRunRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        initialize_database()

    @staticmethod
    def save(day, terrain, slope, movement=None, session_type=SessionType.EASY_RUN, **measurements):
        values = dict(
            field_type=terrain.label,
            slope_type=slope.label,
            dynamic_type=movement.label if movement else None,
            distance=Decimal("10.0"), velocity=Decimal("9.0"),
            mean_HR=130, max_HR=145, RPE=Decimal("3.0"), comment="",
            **{f"Z{i}": timedelta(0) for i in range(1, 6)},
        )
        values.update(measurements)
        return create_session(day, session_type, values)

    def test_only_easy_runs_are_read_with_newest_first_and_duplicates_preserved(self):
        self.assertEqual(get_sessions(SessionType.EASY_RUN), [])
        self.save(date(2026, 12, 31), Terrain.ROAD, Slope.FLAT)
        self.save(date(2027, 1, 1), Terrain.TREADMILL, Slope.HILLY, Movement.WALK)
        self.save(date(2027, 1, 1), Terrain.TREADMILL, Slope.HILLY, Movement.RUN)
        self.save(date(2027, 1, 1), Terrain.TREADMILL, Slope.HILLY, Movement.RUN)
        self.save(date(2027, 1, 2), Terrain.TECHNICAL, Slope.HILLY,
                  session_type=SessionType.LONG_RUN)
        create_session(date(2027, 1, 2), SessionType.LEG_STRENGTH)
        self.assertEqual(get_sessions(SessionType.EASY_RUN), [
            EnduranceSession(date(2027, 1, 1), "Tapis", "Avec pente", "Course",
                           distance=Decimal("10.0"), velocity=Decimal("9.0"),
                           mean_hr=130, max_hr=145, rpe=Decimal("3.0")),
            EnduranceSession(date(2027, 1, 1), "Tapis", "Avec pente", "Course",
                           distance=Decimal("10.0"), velocity=Decimal("9.0"),
                           mean_hr=130, max_hr=145, rpe=Decimal("3.0")),
            EnduranceSession(date(2027, 1, 1), "Tapis", "Avec pente", "Marche",
                           distance=Decimal("10.0"), velocity=Decimal("9.0"),
                           mean_hr=130, max_hr=145, rpe=Decimal("3.0")),
            EnduranceSession(date(2026, 12, 31), "Route", "Sans pente", None,
                           distance=Decimal("10.0"), velocity=Decimal("9.0"),
                           mean_hr=130, max_hr=145, rpe=Decimal("3.0")),
        ])

    def test_measurements_and_optional_weather_are_loaded_from_storage(self):
        self.save(date(2026, 11, 10), Terrain.ROAD, Slope.FLAT,
                  distance=Decimal("12.3"), velocity=Decimal("9.5"),
                  elevation_gain=0, temperature=-2, weather="Vent & pluie")
        self.save(date(2026, 11, 11), Terrain.TREADMILL, Slope.HILLY, Movement.WALK,
                  inclination=Decimal("5.5"))
        newest, oldest = get_sessions(SessionType.EASY_RUN)
        self.assertEqual(newest.inclination, Decimal("5.5"))
        self.assertIsNone(newest.weather)
        self.assertEqual(
            (oldest.distance, oldest.velocity, oldest.elevation_gain,
             oldest.temperature, oldest.weather),
            (Decimal("12.3"), Decimal("9.5"), 0, -2, "Vent & pluie"),
        )

    def test_heart_rates_zone_durations_rpe_and_comment_are_loaded(self):
        durations = [timedelta(days=1, seconds=i) for i in range(1, 6)]
        comment = "Bonne séance\nÀ refaire !"
        self.save(date(2026, 11, 10), Terrain.ROAD, Slope.FLAT,
                  mean_HR=142, max_HR=165, RPE=Decimal("6.5"), comment=comment,
                  **{f"Z{i}": duration for i, duration in enumerate(durations, 1)})
        session, = get_sessions(SessionType.EASY_RUN)
        self.assertEqual((session.mean_hr, session.max_hr), (142, 165))
        self.assertEqual([session.z1, session.z2, session.z3, session.z4, session.z5], durations)
        self.assertEqual(session.rpe, Decimal("6.5"))
        self.assertEqual(session.comment, comment)

    def test_each_endurance_query_reads_only_its_own_sessions_in_date_order(self):
        types = (SessionType.LONG_RUN, SessionType.EASY_RUN, SessionType.STEADY_RUN)
        for index, session_type in enumerate(types):
            for day in (date(2026, 11, 8), date(2026, 11, 10), date(2026, 11, 10)):
                self.save(day, Terrain.TREADMILL, Slope.HILLY, Movement.RUN,
                          session_type=session_type, distance=Decimal(index + 1),
                          comment=session_type.value, Z1=timedelta(seconds=30),
                          Z2=timedelta(seconds=70))
        for index, session_type in enumerate(types):
            with self.subTest(session_type=session_type):
                sessions = get_sessions(session_type)
                self.assertEqual([row.date for row in sessions],
                                 [date(2026, 11, 10), date(2026, 11, 10), date(2026, 11, 8)])
                self.assertTrue(all(row.comment == session_type.value for row in sessions))
                self.assertTrue(all(row.distance == Decimal(index + 1) for row in sessions))
                self.assertTrue(all(row.z1 == timedelta(seconds=30) for row in sessions))
                self.assertTrue(all(row.z2 == timedelta(seconds=70) for row in sessions))

    def test_unsupported_session_types_are_rejected_before_opening_the_database(self):
        with patch("trail_mania.session_repository.create_database_engine") as engine:
            for session_type in (SessionType.LEG_STRENGTH, "Inconnu"):
                with self.subTest(session_type=session_type), self.assertRaises(ValueError):
                    get_sessions(session_type)
            engine.assert_not_called()


class EnduranceSessionsTests(unittest.TestCase):
    session_type = SessionType.EASY_RUN

    def setUp(self):
        self.enterContext(patch.object(ft.Control, "update", autospec=True))
        self.sessions = [
            EnduranceSession(date(2026, 11, 10), "Route", "Sans pente", None),
            EnduranceSession(date(2026, 11, 9), "Terrain roulant", "Avec pente", None),
            EnduranceSession(date(2026, 11, 8), "Terrain technique", "Avec pente", None),
            EnduranceSession(date(2026, 11, 7), "Tapis", "Sans pente", None),
            EnduranceSession(date(2026, 11, 6), "Tapis", "Avec pente", "Marche"),
            EnduranceSession(date(2026, 11, 5), "Tapis", "Avec pente", "Course"),
            EnduranceSession(date(2026, 11, 5), "Tapis", "Avec pente", "Course"),
        ]
        self.reader = self.enterContext(patch.object(
            _session_list, "get_sessions", return_value=self.sessions,
        ))
        self.view = SessionsView()
        self.view._open_session(self.session_type)
        self.panel = self.view._session_list
        self.filters = self.panel.filters
        self.table = self.panel.table
        self.reader.assert_called_once_with(self.session_type)

    def choose(self, group, choice, value=True):
        checkbox = getattr(self.filters, f"{group}_choices")[choice]
        checkbox.value = value
        checkbox.on_change(ft.Event("change", checkbox))

    def rows(self):
        return [
            [cell.content.content.value if isinstance(cell.content.content, ft.Text)
             else getattr(cell.content.content, "semantics_label", getattr(cell.content.content, "label", None))
             for cell in row.cells]
            for row in self.table._table.rows
        ]

    def test_initial_table_has_headers_but_no_rows_until_a_filter_is_selected(self):
        self.assertEqual(self.view.content.controls[0].controls[1].value, self.session_type)
        self.assertEqual(
            [column.label.value for column in self.table._table.columns],
            ["Date", "Terrain", "Pente", "M / C", "Dist", "Incli",
             "D+", "Vit", "Temp", "Météo", "FC moy", "FC max",
             "% Z1", "% Z2", "% Z3", "% Z4", "% Z5", "RPE", "Commentaire"],
        )
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.table._empty_message.visible)
        self.assertFalse(self.filters.movement_field.visible)
        self.choose("terrain", Terrain.ROAD)
        self.assertEqual(self.rows(), [])
        self.choose("slope", Slope.FLAT)
        self.assertEqual(self.rows()[0], ["10/11/2026", "Route", "Sans pente", "—"] + ["—"] * 15)
        self.choose("terrain", Terrain.TREADMILL)
        self.assertEqual(len(self.rows()), 2)
        self.choose("slope", Slope.HILLY)
        self.assertEqual(len(self.rows()), 2)
        self.choose("movement", Movement.RUN)
        self.assertEqual(self.rows()[-1], ["05/11/2026", "Tapis", "Avec pente", "Course"] + ["—"] * 15)
        self.assertFalse(self.table._empty_message.visible)
        self.assertTrue(self.filters.movement_field.visible)

    def test_clearing_all_filters_hides_all_rows_even_with_cached_movement_choices(self):
        self.choose("terrain", Terrain.TREADMILL)
        self.choose("slope", Slope.HILLY)
        self.choose("movement", Movement.WALK)
        self.assertEqual(len(self.rows()), 1)
        self.choose("terrain", Terrain.TREADMILL, False)
        self.choose("slope", Slope.HILLY, False)
        self.assertTrue(self.filters.movement_choices[Movement.WALK].value)
        self.assertFalse(self.filters.movement_field.visible)
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.table._empty_message.visible)
        self.view.refresh()
        self.assertEqual(self.rows(), [])

    def test_multiple_choices_are_combined_with_or_and_groups_with_and(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("terrain", Terrain.ROLLING)
        self.assertEqual(self.rows(), [])
        self.choose("slope", Slope.HILLY)
        self.assertEqual([row[1] for row in self.rows()], ["Terrain roulant"])
        self.choose("slope", Slope.FLAT)
        self.assertEqual(len(self.rows()), 2)
        self.choose("terrain", Terrain.ROAD, False)
        self.choose("terrain", Terrain.ROLLING, False)
        self.assertEqual(self.rows(), [])
        self.reader.assert_called_once()

    def test_movement_filter_only_applies_to_inclined_treadmills(self):
        self.choose("terrain", Terrain.TREADMILL)
        self.choose("slope", Slope.HILLY)
        self.assertTrue(self.filters.movement_field.visible)
        self.assertEqual(self.rows(), [])
        self.choose("movement", Movement.WALK)
        self.assertEqual([row[3] for row in self.rows()], ["Marche"])
        self.choose("movement", Movement.RUN)
        self.assertEqual(len(self.rows()), 3)
        self.choose("movement", Movement.RUN, False)
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.assertEqual([row[3] for row in self.rows()], ["—", "—", "Marche"])
        self.choose("slope", Slope.HILLY, False)
        self.assertFalse(self.filters.movement_field.visible)
        self.assertEqual([row[2] for row in self.rows()], ["Sans pente", "Sans pente"])
        self.choose("slope", Slope.FLAT, False)
        self.assertEqual(self.rows(), [])  # A slope remains required even with cached movement.

    def test_empty_results_keep_headers_and_show_a_message(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.HILLY)
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.table._empty_message.visible)
        self.assertEqual(len(self.table._table.columns), 19)
        self.choose("slope", Slope.HILLY, False)
        self.assertEqual(self.rows(), [])
        self.choose("slope", Slope.FLAT)
        self.assertEqual(len(self.rows()), 1)
        self.assertFalse(self.table._empty_message.visible)

    def test_returning_to_tab_reloads_data_and_preserves_filters(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        terrain_checkbox = self.filters.terrain_choices[Terrain.ROAD]
        self.reader.return_value = self.sessions + [
            EnduranceSession(date(2026, 11, 11), "Route", "Sans pente", None),
        ]
        page = Mock()
        container = ft.Container()
        nav = ft.NavigationBar(selected_index=0)
        change_page(ft.Event("change", nav), page, [self.view], container)
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(terrain_checkbox.value)
        self.assertIs(self.filters.terrain_choices[Terrain.ROAD], terrain_checkbox)
        self.assertIs(container.content, self.view)
        self.assertEqual(self.reader.call_count, 2)
        page.update.assert_called_once()

    def test_measurement_units_zero_missing_values_and_weather_symbols(self):
        self.reader.return_value = [
            EnduranceSession(
                date(2026, 11, 10), "Route", "Sans pente", None,
                distance=Decimal("12.3"), inclination=Decimal("0.0"),
                elevation_gain=0, velocity=Decimal("9.5"), temperature=-2,
                weather=weather,
            )
            for weather in ("Normal", "Vent", "Pluie", "Vent & pluie", None)
        ]
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.view.refresh()
        self.assertEqual(self.rows()[0][4:9], ["12,3 km", "0,0 %", "0 m", "9,5 km/h", "-2 °C"])
        self.assertEqual([row[9] for row in self.rows()],
                         ["Normal", "Vent", "Pluie", "Vent & pluie", "—"])
        for row in self.table._table.rows[:4]:
            self.assertNotIsInstance(row.cells[9].content.content, ft.Text)

    def test_large_table_has_its_own_bounded_vertical_scroll_area(self):
        self.reader.return_value = self.sessions * 50
        for terrain in Terrain:
            self.choose("terrain", terrain)
        for slope in Slope:
            self.choose("slope", slope)
        for movement in Movement:
            self.choose("movement", movement)
        self.view.refresh()
        self.assertEqual(len(self.rows()), 350)
        viewport = self.table._rows_viewport
        self.assertTrue(self.panel.expand)
        self.assertTrue(viewport.expand)
        self.assertEqual(viewport.scroll, ft.ScrollMode.ALWAYS)
        self.assertEqual(self.table._horizontal_viewport.scroll, ft.ScrollMode.AUTO)
        self.assertIsNone(self.panel.scroll)
        self.assertIsNone(self.view.content.scroll)

    def test_zone_percentages_use_the_sum_of_all_five_durations(self):
        session = replace(
            self.sessions[0], mean_hr=142, max_hr=165, rpe=Decimal("6.5"),
            z1=timedelta(seconds=60), z2=timedelta(seconds=30),
            z3=timedelta(0), z4=timedelta(seconds=5), z5=timedelta(seconds=5),
            comment="Bonne séance\nÀ refaire !",
        )
        self.reader.return_value = [session]
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.view.refresh()
        self.assertEqual(self.rows()[0][10:], [
            "142 bpm", "165 bpm", "60 %", "30 %", "0 %", "5 %", "5 %",
            "6,5", session.comment,
        ])
        self.assertEqual(self.table._table.rows[0].cells[-1].content.content.tooltip, session.comment)

    def test_sticky_header_and_rows_share_horizontal_scroll_and_column_widths(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        header = self.table._table_header
        body = self.table._table
        horizontal = self.table._horizontal_viewport
        stack = horizontal.controls[0]
        self.assertIs(stack.controls[-1].content, header)
        self.assertIs(stack.controls[0].content, body)
        self.assertEqual(body.heading_row_height, 0)
        self.assertGreater(header.heading_row_height, 0)
        self.assertEqual(header.width, body.width)
        self.assertEqual(
            [column.label.width for column in header.columns],
            [cell.content.width for cell in body.rows[0].cells],
        )

    def test_filters_scroll_away_before_header_pins_and_reappear_when_scrolling_back(self):
        self.reader.return_value = self.sessions * 10
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.view.refresh()
        checkbox = self.filters.terrain_choices[Terrain.ROAD]
        self.table._on_filters_size_change(ft.LayoutSizeChangeEvent(
            "size_change", self.table._filters_section, width=800, height=200,
        ))
        for offset, header_top in ((0, 0), (100, 0), (200, 0), (300, 100), (100, 0), (0, 0)):
            with self.subTest(offset=offset):
                self.table._on_vertical_scroll(ft.OnScrollEvent(
                    "scroll", self.table._rows_viewport,
                    event_type=ft.ScrollType.UPDATE, pixels=offset,
                    min_scroll_extent=0, max_scroll_extent=500, viewport_dimension=400,
                ))
                self.assertEqual(self.table._sticky_header.top, header_top)
                self.assertEqual(200 - offset + header_top, max(0, 200 - offset))
        self.assertIs(self.filters.terrain_choices[Terrain.ROAD], checkbox)
        self.assertTrue(checkbox.value)
        self.assertEqual(len(self.rows()), 10)

    def test_measured_column_width_is_shared_by_header_rows_and_later_refreshes(self):
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        old_width = self.table._table.width
        old_distance_width = self.table._table.rows[0].cells[4].content.width
        self.table._on_column_size(ft.LayoutSizeChangeEvent(
            "size_change", self.table._column_measurements, width=58.4, height=20,
        ), 4)
        for table in (self.table._table_header, self.table._table):
            self.assertEqual(table.columns[4].label.width, 59)
            self.assertEqual(table.width, old_width - old_distance_width + 59)
        self.assertEqual(self.table._table_stack.width, self.table._table.width)
        self.assertEqual(self.table._table.rows[0].cells[4].content.width, 59)
        self.view.refresh()
        self.assertEqual(self.table._table.rows[0].cells[4].content.width, 59)

    def test_filtering_and_refresh_clamp_a_header_pinned_over_removed_rows(self):
        self.reader.return_value = self.sessions * 20
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.view.refresh()
        self.table._on_filters_size_change(ft.LayoutSizeChangeEvent(
            "size_change", self.table._filters_section, width=800, height=200,
        ))
        self.table._on_vertical_scroll(ft.OnScrollEvent(
            "scroll", self.table._rows_viewport,
            event_type=ft.ScrollType.UPDATE, pixels=1000,
            min_scroll_extent=0, max_scroll_extent=1200, viewport_dimension=400,
        ))
        self.assertEqual(self.table._sticky_header.top, 800)
        self.reader.return_value = [self.sessions[0]]
        self.view.refresh()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(
            self.table._sticky_header.top,
            self.table._table_stack.height - self.table._sticky_header.height,
        )
        self.choose("terrain", Terrain.ROAD, False)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.table._sticky_header.top, 0)

    def test_zone_percentages_handle_zero_total_and_durations_over_a_day(self):
        duration = timedelta(days=1, seconds=1)
        self.reader.return_value = [
            replace(self.sessions[0], z1=duration, z2=duration, z3=duration),
            self.sessions[0],
        ]
        self.choose("terrain", Terrain.ROAD)
        self.choose("slope", Slope.FLAT)
        self.view.refresh()
        self.assertEqual(self.rows()[0][12:17], ["33 %", "33 %", "33 %", "0 %", "0 %"])
        self.assertEqual(self.rows()[1][12:17], ["—"] * 5)

    def test_slope_alone_and_incomplete_treadmill_filters_show_no_rows(self):
        self.choose("slope", Slope.HILLY)
        self.assertEqual(self.rows(), [])
        self.choose("terrain", Terrain.TREADMILL)
        self.assertTrue(self.filters.movement_field.visible)
        self.assertEqual(self.rows(), [])
        self.choose("movement", Movement.RUN)
        self.assertEqual([row[3] for row in self.rows()], ["Course", "Course"])
        self.choose("movement", Movement.RUN, False)
        self.assertEqual(self.rows(), [])
        self.choose("slope", Slope.FLAT)
        self.assertEqual([row[2:4] for row in self.rows()], [["Sans pente", "—"]])
        self.choose("slope", Slope.HILLY, False)
        self.assertFalse(self.filters.movement_field.visible)
        self.assertEqual(len(self.rows()), 1)

    def test_back_discards_the_table(self):
        self.view.content.controls[0].controls[0].on_click(None)
        self.assertIsNone(self.view._session_list)
        self.assertIs(self.view.content, self.view._session_choices)
        self.view.refresh()
        self.reader.assert_called_once()


class LongRunSessionsTests(EnduranceSessionsTests):
    session_type = SessionType.LONG_RUN


class SteadyRunSessionsTests(EnduranceSessionsTests):
    session_type = SessionType.STEADY_RUN


class SessionsSerializationTests(unittest.TestCase):
    def test_each_running_family_serializes_through_filtering_refresh_and_back(self):
        def send_patch(view, *, initial=False):
            changes, _, _ = ObjectPatch.from_diff(
                None if initial else view, view, control_cls=BaseControl,
            )
            encoded = msgpack.packb(
                changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl),
            )
            return msgpack.unpackb(encoded, strict_map_key=False)

        for session_type in SessionType:
            if not session_type.has_details:
                continue
            with self.subTest(session_type=session_type), patch.object(ft.Control, "update"):
                record = (
                    IntervalSession(date.today(), "Route", "Sans pente", None, session_type=session_type)
                    if session_type.has_format
                    else EnduranceSession(date.today(), "Route", "Sans pente", None)
                )
                with patch.object(_session_list, "get_sessions", return_value=[record]) as reader:
                    view = SessionsView()
                    send_patch(view, initial=True)
                    view._open_session(session_type)
                    self.assertTrue(send_patch(view))
                    panel = view._session_list
                    filters = panel.filters
                    choices = [filters.terrain_choices[Terrain.ROAD], filters.slope_choices[Slope.FLAT]]
                    if session_type.has_format:
                        choices.append(filters.format_choices[record.session_format])
                    for checkbox in choices:
                        checkbox.value = True
                        checkbox.on_change(ft.Event("change", checkbox))
                        self.assertTrue(send_patch(view))
                    self.assertEqual(len(panel.table._table.rows), 1)
                    view.refresh()
                    send_patch(view)
                    reader.assert_called_with(session_type)
                    self.assertEqual(reader.call_count, 2)
                    self.assertIs(view._session_list, panel)
                    view._back_to_choices()
                    self.assertTrue(send_patch(view))
                    self.assertIsNone(view._session_list)
                    view._open_session(session_type)
                    self.assertTrue(send_patch(view))
                    self.assertIsNot(view._session_list, panel)
                    self.assertEqual(view._session_list.table._table.rows, [])
                    self.assertEqual(
                        tuple(view._session_list.filters.format_choices),
                        SESSION_FORMATS.get(session_type, ()),
                    )


if __name__ == "__main__":
    unittest.main()
