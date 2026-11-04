import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import flet as ft
from sqlalchemy import MetaData, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.components import (
    CommentsInput, DateSelector, DistanceInput, DurationInput, ElevationInput,
    HeartRateInput, InclinationInput, RPEInput, SpeedInput, TemperatureInput,
    WeatherSelector, ZoneDurationInput,
)
from trail_mania.components.numeric_input import NumericInput
from trail_mania.database import create_database_engine, initialize_database
from trail_mania.models import Base, Session, SessionSortieLongue
from trail_mania.session_repository import DETAIL_MODELS, get_calendar_sessions_by_date, get_sessions
from trail_mania.views.add_session._session_form import SessionForm
from trail_mania.views.add_session import AddSessionView


VARIANTS = (
    ("Sortie longue", None, 0),
    ("Endurance fondamentale", None, 0),
    ("Endurance active", None, 0),
    ("Seuil", "continuous", 0),
    ("Seuil", "three_repetitions", 3),
    ("VO2max", "four_repetitions", 4),
    ("VO2max", "five_repetitions", 5),
    ("VO2max", "six_repetitions", 6),
)
SELECTED_DATE = date(2026, 1, 3)


class SessionSubmissionTests(unittest.TestCase):
    def test_weekly_descriptions_use_saved_configuration_and_interval_format(self):
        for title, session_format, repetitions in VARIANTS:
            for terrain, slope, movement, location in (
                ("road", "flat", None, "Route - Sans pente"),
                ("technical", "hilly", None, "Terrain technique - Avec pente"),
                ("treadmill", "flat", None, "Tapis - Sans pente"),
                ("treadmill", "hilly", "walk", "Tapis - Avec pente - Marche"),
                ("treadmill", "hilly", "run", "Tapis - Avec pente - Course"),
            ):
                with self.subTest(title=title, format=session_format, location=location):
                    form = self.make_form(title, session_format, terrain, slope, movement)
                    self.fill_form(form)
                    self.click(form)
                    sessions = get_calendar_sessions_by_date(SELECTED_DATE, SELECTED_DATE)
                    last = sessions[SELECTED_DATE][-1]
                    expected = location
                    if session_format is not None:
                        expected += f" - x{repetitions or 1}"
                    self.assertEqual(last.session_type, title)
                    self.assertEqual(last.description, expected)
                    self.assertEqual(last.record, get_sessions(title)[0])
        self.assertEqual(get_calendar_sessions_by_date(date(2020, 1, 1), date(2020, 1, 7)), {})

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {
            "FLET_APP_STORAGE_DATA": str(Path(directory.name) / "data"),
        }))
        initialize_database()
        self.engine = create_database_engine()
        self.addCleanup(self.engine.dispose)
        self.enterContext(patch.object(AddSessionView, "update"))
        self.enterContext(patch.object(SessionForm, "update"))
        self.enterContext(patch.object(ft.SegmentedButton, "update"))
        self.page = Mock()
        self.enterContext(patch.object(
            AddSessionView, "page", new_callable=PropertyMock, return_value=self.page,
        ))
        self.view = AddSessionView()

    def make_form(self, title, session_format=None, terrain="road", slope="flat", movement=None):
        self.view._open_session(title)
        form = self.view.content
        for selector, value in (
            (form.terrain_selector, terrain),
            (form.slope_selector, slope),
            (form.movement_selector, movement),
            (form.format_selector, session_format),
        ):
            if selector is not None and value is not None:
                selector.content.selected = [value]
                selector.content.on_change(SimpleNamespace(control=selector.content))
        self.assertIsNotNone(form.details_form)
        return form.details_form

    def fill_form(self, form, *, fill_zones=True):
        # Set raw client text without triggering blur/on_change: saving must re-read it.
        for control in form.controls:
            if isinstance(control, DateSelector):
                with patch.object(DateSelector, "update"):
                    control._change_date(SimpleNamespace(control=SimpleNamespace(value=SELECTED_DATE)))
            elif isinstance(control, NumericInput):
                index = int(re.search(r"(\d+)$", control.label).group(1)) if control.label[-1:].isdigit() else 1
                if isinstance(control, ZoneDurationInput):
                    if not fill_zones:
                        continue
                    value = f"25:02:{index:02d}"
                elif isinstance(control, HeartRateInput):
                    value = str((170 if "max" in control.label else 140) + index)
                elif isinstance(control, SpeedInput):
                    value = f"{8 + index},2" if "OFF" in control.label else f"{12 + index},1"
                else:
                    value = {
                        DistanceInput: "21,3", DurationInput: "2,5" if control.label.endswith("OFF") else "10,5",
                        ElevationInput: "250", InclinationInput: "2,5", TemperatureInput: "-3", RPEInput: "7,5",
                    }[type(control)]
                control._field.value = value
            elif isinstance(control, WeatherSelector):
                control._selector.selected = ["wind_rain"]
            elif isinstance(control, CommentsInput):
                control._field.value = "Belle séance\nÀ refaire !"

    def click(self, form):
        button = form.submit_button
        button.on_click(SimpleNamespace(control=button))
        return button

    def session_count(self):
        with DatabaseSession(self.engine) as db:
            return db.scalar(select(func.count()).select_from(Session))

    def test_buttons_save_all_72_form_variants_with_correct_values_and_nulls(self):
        count = 0
        for title, session_format, repetitions in VARIANTS:
            model = DETAIL_MODELS[title]
            for terrain in ("road", "rolling", "technical", "treadmill"):
                for slope in ("flat", "hilly"):
                    movements = ("walk", "run") if (terrain, slope) == ("treadmill", "hilly") else (None,)
                    for movement in movements:
                        with self.subTest(title=title, format=session_format, terrain=terrain, slope=slope, movement=movement):
                            form = self.make_form(title, session_format, terrain, slope, movement)
                            self.fill_form(form)
                            button = self.click(form)
                            self.assertTrue(button.disabled)
                            count += 1
                            self.assertEqual(self.session_count(), count)
                            self.assertIs(self.view.content, self.view._session_choices)
                            with DatabaseSession(self.engine) as db:
                                parent = db.scalars(select(Session).order_by(Session.id.desc())).first()
                                self.assertEqual(parent.date, SELECTED_DATE)
                                self.assertEqual(parent.session_type, title)
                                detail = db.scalars(select(model).where(model.session_id == parent.id)).one()
                                self.assertEqual(detail.field_type, {
                                    "road": "Route", "rolling": "Terrain roulant",
                                    "technical": "Terrain technique", "treadmill": "Tapis",
                                }[terrain])
                                self.assertEqual(detail.slope_type, "Avec pente" if slope == "hilly" else "Sans pente")
                                self.assertEqual(detail.dynamic_type, {None: None, "walk": "Marche", "run": "Course"}[movement])
                                self.assertEqual(detail.weather, None if terrain == "treadmill" else "Vent & pluie")
                                self.assertEqual(detail.temperature, None if terrain == "treadmill" else -3)
                                self.assertEqual(detail.elevation_gain, None if terrain == "treadmill" else 250)
                                self.assertEqual(detail.inclination, Decimal("2.5") if terrain == "treadmill" and slope == "hilly" else None)
                                self.assertEqual(detail.RPE, Decimal("7.5"))
                                self.assertEqual(detail.comment, "Belle séance\nÀ refaire !")
                                for index in range(1, 6):
                                    self.assertEqual(getattr(detail, f"Z{index}"), timedelta(hours=25, minutes=2, seconds=index))
                                if title not in ("Seuil", "VO2max"):
                                    self.assertEqual(detail.distance, Decimal("21.3"))
                                    self.assertEqual(detail.velocity, Decimal("13.1"))
                                    self.assertEqual(detail.mean_HR, 141)
                                    self.assertEqual(detail.max_HR, 171)
                                else:
                                    self.assertEqual(detail.duration_ON, Decimal("10.5"))
                                    self.assertEqual(detail.duration_OFF, Decimal("2.5") if repetitions else None)
                                    for index in range(1, (3 if title == "Seuil" else 6) + 1):
                                        active = index <= (repetitions or 1)
                                        self.assertEqual(getattr(detail, f"velocity_ON_{index}"), 12 + index + .1 if active else None)
                                        self.assertEqual(getattr(detail, f"mean_HR_ON_{index}"), 140 + index if active else None)
                                        self.assertEqual(getattr(detail, f"max_HR_ON_{index}"), 170 + index if active else None)
                                        if index < (3 if title == "Seuil" else 6):
                                            self.assertEqual(getattr(detail, f"velocity_OFF_{index}"), 8 + index + .2 if index < repetitions else None)
        self.assertEqual(count, 72)

    def test_default_elevation_and_inclination_are_saved_only_when_applicable(self):
        for title, session_format, _ in VARIANTS:
            for terrain, slope, movement in (
                ("road", "flat", None),
                ("treadmill", "flat", None),
                ("treadmill", "hilly", "run"),
            ):
                with self.subTest(title=title, format=session_format, terrain=terrain, slope=slope):
                    form = self.make_form(title, session_format, terrain, slope, movement)
                    defaults = {
                        name: control._field.value for name, control in form.inputs.items()
                        if name in ("elevation_gain", "inclination")
                    }
                    self.fill_form(form)
                    for name, text in defaults.items():
                        form.inputs[name]._field.value = text
                    self.click(form)
                    with DatabaseSession(self.engine) as db:
                        detail = db.scalars(select(DETAIL_MODELS[title]).order_by(
                            DETAIL_MODELS[title].id.desc(),
                        )).first()
                        self.assertEqual(detail.elevation_gain, 0 if terrain == "road" else None)
                        self.assertEqual(
                            detail.inclination,
                            Decimal("0.0") if terrain == "treadmill" and slope == "hilly" else None,
                        )

    def test_muscu_button_creates_only_parent_and_ignores_duplicate_click(self):
        self.view._open_session("Muscu jambes")
        form = self.view.content.details_form
        self.fill_form(form)
        button = self.click(form)
        button.on_click(SimpleNamespace(control=button))
        self.assertEqual(
            get_calendar_sessions_by_date(SELECTED_DATE, SELECTED_DATE)[SELECTED_DATE][0].description,
            "",
        )
        with DatabaseSession(self.engine) as db:
            parent = db.scalars(select(Session)).one()
            self.assertEqual(parent.session_type, "Muscu jambes")
            self.assertEqual(parent.date, SELECTED_DATE)
            for model in DETAIL_MODELS.values():
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0)

    def test_required_fields_block_empty_form_then_allow_correction(self):
        form = self.make_form("Sortie longue")
        button = self.click(form)
        self.assertFalse(button.disabled)
        self.assertEqual(self.session_count(), 0)
        required = [control for control in form.controls if isinstance(
            control, (DistanceInput, SpeedInput, HeartRateInput, RPEInput),
        )]
        self.assertTrue(all(control._field.error == "Champ obligatoire" for control in required))
        self.fill_form(form)
        self.click(form)
        self.assertEqual(self.session_count(), 1)
        self.assertTrue(all(control._field.error is None for control in required))

    def test_invalid_optional_and_zone_inputs_are_not_silently_saved_as_null(self):
        for field_class, bad_value in ((TemperatureInput, "invalide"), (ZoneDurationInput, "01:99:00"), (HeartRateInput, "221")):
            with self.subTest(field=field_class):
                form = self.make_form("Sortie longue")
                self.fill_form(form)
                control = next(control for control in form.controls if isinstance(control, field_class))
                control._field.value = bad_value
                button = self.click(form)
                self.assertFalse(button.disabled)
                self.assertIsNotNone(control._field.error)
                self.assertEqual(self.session_count(), 0)
                self.assertIs(self.view.content.details_form, form)

    def test_negative_inclination_blocks_submission(self):
        form = self.make_form("Sortie longue", terrain="treadmill", slope="hilly", movement="run")
        self.fill_form(form)
        control = form.inputs["inclination"]
        control._field.value = "-0,5"
        button = self.click(form)
        self.assertFalse(button.disabled)
        self.assertIsNotNone(control._field.error)
        self.assertEqual(self.session_count(), 0)

    def test_nullable_visible_fields_can_be_left_empty(self):
        form = self.make_form("Sortie longue")
        self.fill_form(form, fill_zones=False)
        for control in form.controls:
            if isinstance(control, (TemperatureInput, ElevationInput)):
                control._field.value = ""
            elif isinstance(control, WeatherSelector):
                control._selector.selected = []
            elif isinstance(control, CommentsInput):
                control._field.value = ""
        self.click(form)
        with DatabaseSession(self.engine) as db:
            detail = db.scalars(select(SessionSortieLongue)).one()
            self.assertIsNone(detail.temperature)
            self.assertIsNone(detail.elevation_gain)
            self.assertIsNone(detail.weather)
            self.assertEqual(detail.comment, "")
            for index in range(1, 6):
                self.assertEqual(getattr(detail, f"Z{index}"), timedelta(0))

    def test_failure_after_parent_insert_rolls_back_both_rows_and_can_be_retried(self):
        form = self.make_form("Sortie longue")
        self.fill_form(form)

        def fail_insert(mapper, connection, target):
            raise IntegrityError("INSERT", {}, Exception("simulated failure"))

        event.listen(SessionSortieLongue, "before_insert", fail_insert)
        try:
            with self.assertLogs("trail_mania.views.add_session.add_session_view", level="ERROR"):
                button = self.click(form)
        finally:
            event.remove(SessionSortieLongue, "before_insert", fail_insert)
        self.assertFalse(button.disabled)
        self.assertFalse(self.view._saving)
        self.assertEqual(self.session_count(), 0)
        self.assertIs(self.view.content.details_form, form)
        self.assertIn("Impossible", self.page.show_dialog.call_args.args[0].content.value)
        self.click(form)
        self.assertEqual(self.session_count(), 1)

    def test_duplicate_click_does_not_insert_again(self):
        form = self.make_form("Sortie longue")
        self.fill_form(form)
        self.click(form)
        self.click(form)
        self.assertEqual(self.session_count(), 1)

    def test_click_while_saving_is_ignored(self):
        form = self.make_form("Sortie longue")
        self.fill_form(form)
        self.view._saving = True
        self.click(form)
        self.assertEqual(self.session_count(), 0)

    def test_submission_from_a_closed_form_is_ignored(self):
        form = self.make_form("Sortie longue")
        self.fill_form(form)
        self.view.content.controls[0].controls[0].on_click(SimpleNamespace())
        self.click(form)
        self.assertEqual(self.session_count(), 0)
        self.assertIs(self.view.content, self.view._session_choices)
        self.page.show_dialog.assert_not_called()

    def test_submission_from_replaced_measurements_is_ignored(self):
        previous = self.make_form("Seuil", "continuous")
        self.fill_form(previous)
        session_form = self.view.content
        selector = session_form.format_selector.content
        selector.selected = ["three_repetitions"]
        selector.on_change(SimpleNamespace(control=selector))
        current = session_form.details_form
        self.fill_form(current)
        self.click(previous)
        self.assertEqual(self.session_count(), 0)
        self.assertIs(self.view.content.details_form, current)
        self.click(current)
        self.assertEqual(self.session_count(), 1)

    def test_weather_migration_preserves_all_five_populated_detail_tables(self):
        legacy = MetaData()
        for table in Base.metadata.sorted_tables:
            copy = table.to_metadata(legacy)
            if "weather" in copy.c:
                copy.c.weather.nullable = False
        Base.metadata.drop_all(self.engine)
        legacy.create_all(self.engine)
        for title, session_format, _ in VARIANTS:
            form = self.make_form(title, session_format)
            self.fill_form(form)
            self.click(form)
        with self.engine.connect() as connection:
            before = {table.name: connection.execute(select(table).order_by(table.c.id)).all()
                      for table in Base.metadata.sorted_tables}
        initialize_database()
        initialize_database()
        with self.engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                self.assertEqual(connection.execute(select(table).order_by(table.c.id)).all(), before[table.name])
                if "weather" in table.c:
                    columns = inspect(connection).get_columns(table.name)
                    self.assertTrue(next(column["nullable"] for column in columns if column["name"] == "weather"))
                    connection.execute(text(f'UPDATE "{table.name}" SET weather = NULL'))
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
        # The migrated table now accepts a real treadmill form without weather.
        form = self.make_form("VO2max", "four_repetitions", "treadmill")
        self.fill_form(form)
        self.click(form)
        self.assertEqual(self.session_count(), 9)


if __name__ == "__main__":
    unittest.main()
