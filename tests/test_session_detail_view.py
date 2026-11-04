import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from math import pi
from unittest.mock import patch

import flet as ft
import flet.canvas as cv
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack

from trail_mania.session_colors import SESSION_OPTIONS
from trail_mania.session_records import EnduranceSession, IntervalSession, StrengthSession
from trail_mania.session_types import SessionType, Slope, Terrain
from trail_mania.views.sessions import SessionsView, _session_list
from trail_mania.views.sessions.session_detail_view import SessionDetailView


class SessionDetailTests(unittest.TestCase):
    def setUp(self):
        self.session = EnduranceSession(
            date(2026, 11, 4), "Tapis", "Avec pente", "Marche",
            distance=Decimal("12.3"), inclination=Decimal("0.0"),
            elevation_gain=0, velocity=Decimal("9.5"), temperature=-2,
            weather="Vent & pluie", mean_hr=142, max_hr=165,
            rpe=Decimal("6.5"), comment="Première ligne\n" + "Commentaire complet " * 100,
            z1=timedelta(days=1), z2=timedelta(hours=12), z5=timedelta(hours=12),
        )

    def detail(self, record=None):
        return SessionDetailView(session=record or self.session, session_type=SessionType.EASY_RUN)

    def test_detail_rejects_measurements_from_another_session_family(self):
        mismatches = (
            (self.session, SessionType.LEG_STRENGTH),
            (self.session, SessionType.THRESHOLD),
            (StrengthSession(date.today()), SessionType.EASY_RUN),
            (IntervalSession(date.today(), "Route", "Sans pente", None), SessionType.VO2MAX),
        )
        for record, family in mismatches:
            with self.subTest(record=type(record), family=family):
                with self.assertRaises(ValueError):
                    SessionDetailView(session=record, session_type=family)

    @staticmethod
    def rows(detail, section):
        return detail.controls[section].controls[0].rows

    def test_tables_preserve_units_zero_icons_labels_and_full_comment(self):
        detail = self.detail()
        rows = self.rows(detail, 2)
        self.assertEqual([row.cells[0].content.value for row in rows], [
            "Date", "Terrain", "Pente", "M / C", "Distance", "Inclinaison", "Dénivelé",
            "Vitesse", "Température", "Météo", "RPE",
        ])
        values = [row.cells[1].content.content for row in rows]
        self.assertEqual(values[0].value, "04/11/2026")
        for index, label in ((1, "Tapis"), (2, "Avec pente"), (3, "Marche"), (9, "Vent & pluie")):
            self.assertIsInstance(values[index], ft.Row)
            self.assertEqual(values[index].controls[1].value, label)
            self.assertNotIsInstance(values[index].controls[0], ft.Text)
        self.assertEqual([values[i].value for i in (4, 5, 6, 7, 8, 10)],
                         ["12,3 km", "0,0 %", "0 m", "9,5 km/h", "-2 °C", "6,5"])
        self.assertEqual(detail.controls[7].value, "Commentaire")
        comment = detail.controls[8].content
        self.assertEqual(comment.value, self.session.comment)
        self.assertIsNone(comment.max_lines)
        self.assertEqual([row.cells[1].content.content.value for row in self.rows(detail, 4)],
                         ["142 bpm", "165 bpm"])

    def test_pie_uses_unrounded_duration_shares_and_shared_palette(self):
        zones = self.detail().controls[6]
        shapes = [shape for shape in zones.controls[0].content.shapes if isinstance(shape, cv.Arc)]
        self.assertEqual([shape.paint.color for shape in shapes],
                         [SESSION_OPTIONS[i][1] for i in (0, 1, 4)])
        self.assertAlmostEqual(sum(shape.sweep_angle for shape in shapes), 2 * pi)
        self.assertEqual([shape.sweep_angle for shape in shapes], [pi, pi / 2, pi / 2])
        self.assertEqual([item.controls[1].value for item in zones.controls[1].controls],
                         ["Z1 : 50,0 %", "Z2 : 25,0 %", "Z3 : 0,0 %", "Z4 : 0,0 %", "Z5 : 25,0 %"])
        separators = [shape for shape in zones.controls[0].content.shapes if isinstance(shape, cv.Line)]
        outline = zones.controls[0].content.shapes[-1]
        self.assertEqual(len(separators), 3)
        for line in separators:
            self.assertEqual(line.paint.color, ft.Colors.BLACK)
            self.assertEqual(line.paint.stroke_width, outline.paint.stroke_width)

    def test_empty_zones_and_missing_measurements_remain_explicit(self):
        session = EnduranceSession(date.today(), "Route", "Sans pente", "Course")
        detail = self.detail(session)
        rows = self.rows(detail, 2)
        for index in (3, 4, 5, 6, 7, 8, 9, 10):
            self.assertEqual(rows[index].cells[1].content.content.value, "—")
        self.assertEqual(detail.controls[8].content.value, "Aucun commentaire.")
        self.assertEqual(detail.controls[6].controls[0].value, "Aucune durée de zone renseignée.")
        one_zone = self.detail(replace(session, z3=timedelta(seconds=1)))
        self.assertAlmostEqual(one_zone.controls[6].controls[0].content.shapes[0].sweep_angle, 2 * pi)
        self.assertFalse(any(isinstance(shape, cv.Line)
                             for shape in one_zone.controls[6].controls[0].content.shapes))

    def test_supported_rows_open_correct_record_and_back_preserves_filters(self):
        def serialize(view):
            changes, _, _ = ObjectPatch.from_diff(None, view, control_cls=BaseControl)
            return msgpack.packb(changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl))

        with patch.object(ft.Control, "update"), patch.object(
            _session_list, "get_sessions", return_value=[
                replace(self.session, terrain="Route", slope="Sans pente", movement=None),
                replace(self.session, terrain="Route", slope="Sans pente", movement=None, comment="Deuxième"),
            ],
        ) as reader:
            for session_type in (SessionType.EASY_RUN, SessionType.STEADY_RUN, SessionType.LONG_RUN):
                view = SessionsView()
                view._open_session(session_type)
                content = view.content
                panel = view._session_list
                panel.filters.terrain_choices[Terrain.ROAD].value = True
                panel.filters.slope_choices[Slope.FLAT].value = True
                panel._on_filter_change()
                row = panel.table._table.rows[1]
                row.on_select_change(ft.Event("select_change", row))
                self.assertIsInstance(view.content, SessionDetailView)
                self.assertEqual(view.content.controls[0].controls[1].value, session_type)
                self.assertEqual(view.content.session.comment, "Deuxième")
                back_button = view.content.controls[0].controls[0]
                self.assertEqual(back_button.icon, ft.Icons.ARROW_BACK)
                self.assertEqual(back_button.tooltip, "Retour à la liste des sessions")
                self.assertTrue(serialize(view))
                view.content.controls[0].controls[0].on_click(None)
                self.assertIs(view.content, content)
                self.assertTrue(panel.filters.terrain_choices[Terrain.ROAD].value)
                self.assertEqual(len(panel.table._table.rows), 2)
                self.assertTrue(serialize(view))
            self.assertEqual(reader.call_count, 3)

    def test_vo2max_shows_six_repetitions_for_all_saved_formats(self):
        for count in (4, 5, 6):
            with self.subTest(repetitions=count):
                session = IntervalSession(
                    date.today(), "Route", "Sans pente", None, session_type=SessionType.VO2MAX,
                    duration_on=Decimal("3.0"), duration_off=Decimal("1.5"),
                    velocity_on=(14.0,) * count + (None,) * (6 - count),
                    velocity_off=(8.0,) * (count - 1) + (None,) * (6 - count),
                    mean_hr_on=(165,) * count + (None,) * (6 - count),
                    max_hr_on=(180,) * count + (None,) * (6 - count),
                    z5=timedelta(minutes=12), comment="Bonne séance VO2max",
                )
                detail = SessionDetailView(session=session, session_type=SessionType.VO2MAX)
                general = {row.cells[0].content.value: row.cells[1].content.content.value
                           for row in self.rows(detail, 2) if isinstance(row.cells[1].content.content, ft.Text)}
                self.assertEqual(detail.controls[0].controls[1].value, "VO2max")
                self.assertNotIn("Format", general)
                self.assertEqual(general["Durée ON"], "3,0 min")
                self.assertEqual(general["Durée OFF"], "1,5 min")
                self.assertEqual(len([label for label in general if label.startswith("Vitesse")]), 6)
                for index in range(1, 7):
                    self.assertEqual(general[f"Vitesse - rep {index}"],
                                     "ON : " + ("14,0 km/h" if index <= count else "—") +
                                     " \u200a/ \u200aOFF : " + ("8,0 km/h" if index < count else "—"))
                heart = self.rows(detail, 4)
                self.assertEqual(len(heart), 6)
                self.assertEqual(heart[-1].cells[1].content.content.value,
                                 "FC moy : 165 bpm \u200a/ \u200aFC max : 180 bpm" if count == 6
                                 else "FC moy : — \u200a/ \u200aFC max : —")
                self.assertEqual(detail.controls[8].content.value, session.comment)
                self.assertTrue(detail.controls[6].controls[0].content.shapes)

                with patch.object(ft.Control, "update"), patch.object(_session_list, "get_sessions", return_value=[session]):
                    view = SessionsView()
                    view._open_session(SessionType.VO2MAX)
                    content = view.content
                    panel = view._session_list
                    panel.filters.terrain_choices[Terrain.ROAD].value = True
                    panel.filters.slope_choices[Slope.FLAT].value = True
                    panel.filters.format_choices[session.session_format].value = True
                    panel._on_filter_change()
                    row, = panel.table._table.rows
                    row.on_select_change(ft.Event("select_change", row))
                    self.assertIs(view.content.session, session)
                    changes, _, _ = ObjectPatch.from_diff(None, view, control_cls=BaseControl)
                    self.assertTrue(msgpack.packb(changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl)))
                    view.content.controls[0].controls[0].on_click(None)
                    self.assertIs(view.content, content)
                    self.assertTrue(panel.filters.format_choices[session.session_format].value)

    def test_threshold_tables_show_durations_and_all_repetitions_without_format(self):
        for repeated in (False, True):
            session = IntervalSession(
                date.today(), "Route", "Sans pente", None,
                duration_on=Decimal("10.5"), duration_off=Decimal("0.0") if repeated else None,
                velocity_on=(12.5, 13.0, 0.0) if repeated else (12.5, None, None),
                velocity_off=(8.0, 0.0) if repeated else (None, None),
                mean_hr_on=(150, 155, 160) if repeated else (150, None, None),
                max_hr_on=(165, 170, 175) if repeated else (165, None, None),
                comment="Séance de seuil", z3=timedelta(minutes=30),
            )
            with self.subTest(repeated=repeated):
                view = SessionDetailView(session=session, session_type=SessionType.THRESHOLD)
                general = {row.cells[0].content.value: row.cells[1].content.content.value
                           for row in self.rows(view, 2) if isinstance(row.cells[1].content.content, ft.Text)}
                self.assertNotIn("Format", general)
                self.assertEqual(general["Durée ON"], "10,5 min")
                self.assertEqual(general["Durée OFF"], "0,0 min" if repeated else "—")
                self.assertEqual(general["Vitesse - rep 1"],
                                 "ON : 12,5 km/h \u200a/ \u200aOFF : " + ("8,0 km/h" if repeated else "—"))
                self.assertEqual(general["Vitesse - rep 3"],
                                 "ON : " + ("0,0 km/h" if repeated else "—") + " \u200a/ \u200aOFF : —")
                heart = self.rows(view, 4)
                self.assertEqual([row.cells[0].content.value for row in heart],
                                 ["Rep 1", "Rep 2", "Rep 3"])
                self.assertEqual(heart[-1].cells[1].content.content.value,
                                 "FC moy : 160 bpm \u200a/ \u200aFC max : 175 bpm" if repeated
                                 else "FC moy : — \u200a/ \u200aFC max : —")
                self.assertEqual(view.controls[8].content.value, session.comment)
                self.assertTrue(view.controls[6].controls[0].content.shapes)

    def test_threshold_list_opens_detail_and_preserves_filters_on_return(self):
        session = IntervalSession(date.today(), "Route", "Sans pente", None, velocity_on=(12.0, None, None))
        with patch.object(ft.Control, "update"), patch.object(_session_list, "get_sessions", return_value=[session]):
            view = SessionsView()
            view._open_session(SessionType.THRESHOLD)
            content = view.content
            panel = view._session_list
            panel.filters.terrain_choices[Terrain.ROAD].value = True
            panel.filters.slope_choices[Slope.FLAT].value = True
            panel.filters.format_choices[session.session_format].value = True
            panel._on_filter_change()
            row, = panel.table._table.rows
            row.on_select_change(ft.Event("select_change", row))
            self.assertIs(view.content.session, session)
            changes, _, _ = ObjectPatch.from_diff(None, view, control_cls=BaseControl)
            self.assertTrue(msgpack.packb(changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl)))
            view.content.controls[0].controls[0].on_click(None)
            self.assertIs(view.content, content)
            self.assertTrue(panel.filters.format_choices[session.session_format].value)


if __name__ == "__main__":
    unittest.main()
