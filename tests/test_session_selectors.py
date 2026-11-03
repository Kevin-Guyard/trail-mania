import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import flet as ft
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack
from flet.utils.object_model import patch_dataclass

from trail_mania.views.add_session import AddSessionView
from trail_mania.views.add_session._session_form import SessionForm
from trail_mania.session_colors import SESSION_OPTIONS
from trail_mania.components import (
    CommentsInput, DateSelector, DistanceInput, DurationInput, ElevationInput, HeartRateInput, InclinationInput,
    RPEInput, ThresholdFormatSelector, SpeedInput, TemperatureInput, VO2maxFormatSelector, WeatherSelector,
    ZoneDurationInput,
)
from trail_mania.components.numeric_input import NumericInput
from trail_mania.app import create_app


class SessionSelectorsTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(SessionForm, "update"))

    def test_picker_opens_each_session_type_and_return_starts_a_fresh_form(self):
        with patch.object(AddSessionView, "update"):
            view = AddSessionView()
            picker = view.content
            labels = picker.controls[1].content.controls
            self.assertEqual(len(labels), 6)
            for label, (title, _) in zip(labels, SESSION_OPTIONS, strict=True):
                label.on_click(SimpleNamespace(control=label))
                form = view.content
                self.assertEqual(form.session_type, title)
                form.controls[0].controls[0].on_click(SimpleNamespace())
                self.assertIs(view.content, picker)
                label.on_click(SimpleNamespace(control=label))
                self.assertIsNot(view.content, form)
                if title.has_details:
                    self.assertIsNone(view.content.terrain_selector.selected)
                    self.assertIsNone(view.content.details_form)

    def assert_secondary_fields(self, content, title, terrain, elevation, session_format=None):
        button = content.controls[-1].controls[1]
        self.assertIsInstance(button, ft.Button)
        self.assertEqual(button.content, "Ajouter")
        self.assertTrue(callable(button.on_click))
        zones = [c for c in content.controls if isinstance(c, ZoneDurationInput)]
        self.assertEqual([c.label for c in zones], ["Z1", "Z2", "Z3", "Z4", "Z5"])
        self.assertEqual(len({id(c) for c in zones}), 5)
        repetition_count = {
            "three_repetitions": 3, "four_repetitions": 4,
            "five_repetitions": 5, "six_repetitions": 6,
        }.get(session_format, 0)
        heart_labels = ["FC moyenne", "FC max"] if not repetition_count else [
            f"FC {kind} ON {index}"
            for index in range(1, repetition_count + 1) for kind in ("moyenne", "max")
        ]
        heart_fields = [c for c in content.controls if isinstance(c, HeartRateInput)]
        self.assertEqual([c.label for c in heart_fields], heart_labels)
        self.assertEqual(len({id(c) for c in heart_fields}), len(heart_labels))
        first_zone = content.controls.index(zones[0])
        self.assertEqual(content.controls[first_zone - len(heart_fields):first_zone], heart_fields)
        if title in ("Seuil", "VO2max"):
            speed_labels = {
                "continuous": ["Vitesse"],
                "three_repetitions": [
                    "Vitesse ON 1", "Vitesse OFF 1", "Vitesse ON 2", "Vitesse OFF 2", "Vitesse ON 3",
                ],
                "four_repetitions": [
                    "Vitesse ON 1", "Vitesse OFF 1", "Vitesse ON 2", "Vitesse OFF 2",
                    "Vitesse ON 3", "Vitesse OFF 3", "Vitesse ON 4",
                ],
                "five_repetitions": [
                    "Vitesse ON 1", "Vitesse OFF 1", "Vitesse ON 2", "Vitesse OFF 2",
                    "Vitesse ON 3", "Vitesse OFF 3", "Vitesse ON 4", "Vitesse OFF 4", "Vitesse ON 5",
                ],
                "six_repetitions": [
                    "Vitesse ON 1", "Vitesse OFF 1", "Vitesse ON 2", "Vitesse OFF 2",
                    "Vitesse ON 3", "Vitesse OFF 3", "Vitesse ON 4", "Vitesse OFF 4",
                    "Vitesse ON 5", "Vitesse OFF 5", "Vitesse ON 6",
                ],
            }
            expected = [(DateSelector, None)]
            if session_format == "continuous":
                expected.append((DurationInput, "Durée"))
            else:
                expected.extend([(DurationInput, "Durée ON"), (DurationInput, "Durée OFF")])
            if terrain != "treadmill":
                expected.append((ElevationInput, "Dénivelé"))
            elif elevation == "hilly":
                expected.append((InclinationInput, "Inclinaison"))
            expected.extend((SpeedInput, label) for label in speed_labels[session_format])
            if terrain != "treadmill":
                expected.extend([(TemperatureInput, "Température"), (WeatherSelector, "Météo")])
            expected.extend((HeartRateInput, label) for label in heart_labels)
            expected.extend((ZoneDurationInput, label) for label in ("Z1", "Z2", "Z3", "Z4", "Z5"))
            expected.extend([(RPEInput, "RPE"), (CommentsInput, None), (ft.Row, None)])
            self.assertIsInstance(content, ft.Column)
            self.assertEqual(
                [(type(control), getattr(control, "label", None)) for control in content.controls],
                expected,
            )
            return
        expected = {
            "outdoor": [
                DateSelector, DistanceInput, ElevationInput, SpeedInput,
                TemperatureInput, WeatherSelector, RPEInput, CommentsInput,
            ],
            "flat": [DateSelector, DistanceInput, SpeedInput, RPEInput, CommentsInput],
            "hilly": [
                DateSelector, DistanceInput, InclinationInput, SpeedInput,
                RPEInput, CommentsInput,
            ],
        }
        self.assertIsInstance(content, ft.Column)
        self.assertEqual(
            [type(control) for control in content.controls],
            expected[elevation if terrain == "treadmill" else "outdoor"][:-2]
            + [HeartRateInput] * 2 + [ZoneDurationInput] * 5 + [RPEInput, CommentsInput, ft.Row],
        )

    def send_patch(self, control, initial=False):
        changes, _, _ = ObjectPatch.from_diff(
            None if initial else control, control, control_cls=BaseControl
        )
        # Serialization records the snapshots used by Flet.
        return msgpack.unpackb(
            msgpack.packb(
                changes.to_message(),
                default=configure_encode_object_for_msgpack(BaseControl),
            ),
            strict_map_key=False,
        )

    def test_terrain_change_sends_elevation_reset_to_client(self):
        for title, _ in SESSION_OPTIONS[:-1]:
            with self.subTest(title=title), patch.object(AddSessionView, "update"):
                view = AddSessionView()
                view._open_session(title)
                self.send_patch(view, initial=True)
                terrain, _, elevation = view.content.controls[2:5]

                def choose_terrain(value):
                    patch_dataclass(terrain.content, {"selected": value})
                    with patch.object(
                        ft.SegmentedButton, "update",
                        side_effect=lambda: self.send_patch(terrain.content),
                    ):
                        terrain.content.on_change(SimpleNamespace(control=terrain.content))
                    return self.send_patch(view)

                choose_terrain(["road"])
                for next_terrain in (["technical"], ["rolling"], []):
                    # Simulate a client selection without calling the Python setter.
                    patch_dataclass(elevation.content, {"selected": ["hilly"]})
                    with patch.object(
                        ft.SegmentedButton,
                        "update",
                        side_effect=lambda: self.send_patch(elevation.content),
                    ):
                        elevation.content.on_change(
                            SimpleNamespace(control=elevation.content)
                        )

                    message = choose_terrain(next_terrain)
                    self.assertIsNone(elevation.selected)
                    # An empty Python value is not enough: the client patch must
                    # also contain the reset of selected.
                    self.assertTrue(
                        any(
                            len(operation) == 4
                            and operation[2] == "selected"
                            and operation[3] == []
                            for operation in message[1:]
                        ),
                        message,
                    )

    def test_movement_is_only_shown_for_treadmill_with_elevation(self):
        for title, _ in SESSION_OPTIONS[:-1]:
            with self.subTest(title=title), patch.object(AddSessionView, "update"):
                view = AddSessionView()
                view._open_session(title)
                self.send_patch(view, initial=True)
                terrain, _, elevation, heading, movement = view.content.controls[2:7]
                self.assertIsNone(movement.selected)
                self.assertFalse(heading.visible)
                self.assertFalse(movement.visible)

                def choose(selector, value):
                    patch_dataclass(selector.content, {"selected": value})
                    with patch.object(
                        ft.SegmentedButton,
                        "update",
                        side_effect=lambda: self.send_patch(selector.content),
                    ):
                        selector.content.on_change(
                            SimpleNamespace(control=selector.content)
                        )
                    return self.send_patch(view)

                for terrain_value in ("road", "rolling", "technical", "treadmill"):
                    choose(terrain, [terrain_value])
                    self.assertFalse(movement.visible)
                    for elevation_value in ("flat", "hilly"):
                        choose(elevation, [elevation_value])
                        expected = terrain_value == "treadmill" and elevation_value == "hilly"
                        self.assertEqual(movement.visible, expected)
                        self.assertEqual(heading.visible, expected)
                        self.assertIsNone(movement.selected)

                self.assertEqual(heading.value, "Marche / Course")
                self.assertEqual(
                    [s.label.content.controls[1].value for s in movement.content.segments],
                    ["Marche", "Course"],
                )
                for upstream in (elevation, terrain):
                    choose(terrain, ["treadmill"])
                    choose(elevation, ["hilly"])
                    choose(movement, ["walk"])
                    message = choose(upstream, ["flat"] if upstream is elevation else ["road"])
                    self.assertFalse(heading.visible)
                    self.assertFalse(movement.visible)
                    self.assertIsNone(movement.selected)
                    self.assertTrue(any(
                        len(op) == 4 and op[2] == "selected" and op[3] == []
                        for op in message[1:]
                    ), message)
                    choose(terrain, ["treadmill"])
                    choose(elevation, ["hilly"])
                    self.assertTrue(movement.visible)
                    self.assertIsNone(movement.selected)

                choose(movement, ["run"])
                choose(elevation, [])
                self.assertFalse(movement.visible)
                self.assertIsNone(movement.selected)

                choose(elevation, ["hilly"])
                choose(movement, ["run"])
                view._back_to_choices()
                view._open_session(title)
                terrain, _, elevation, _, movement = view.content.controls[2:7]
                self.assertIsNone(terrain.selected)
                self.assertIsNone(elevation.selected)
                self.assertIsNone(movement.selected)
                self.assertFalse(view.content.controls[5].visible)
                self.assertFalse(movement.visible)

    def test_strength_view_shows_date_without_main_form(self):
        with patch.object(AddSessionView, "update"):
            view = AddSessionView()
            view._open_session("Muscu jambes")
            self.assertEqual(len(view.content.controls), 2)
            details = view.content.details_form
            self.assertEqual(len(details.controls), 2)
            selector = details.date_input
            self.assertIsInstance(selector, DateSelector)
            self.assertEqual(selector.selected, date.today())
            button = details.submit_button
            self.assertIsInstance(button, ft.Button)
            self.assertEqual(button.content, "Ajouter")
            self.assertTrue(callable(button.on_click))
            header = view.content.controls[0]
            self.assertEqual(header.controls[1].value, "Muscu jambes")
            self.assertEqual(header.controls[0].icon, ft.Icons.ARROW_BACK)
            header.controls[0].on_click(SimpleNamespace(control=header.controls[0]))
            self.assertIs(view.content, view._session_choices)

    def test_secondary_form_requires_all_main_form_choices_and_updates_on_changes(self):
        for title, _ in SESSION_OPTIONS[:-1]:
            if title in ("Seuil", "VO2max"):
                continue  # These forms also require a format, which is tested separately.
            with self.subTest(title=title), patch.object(AddSessionView, "update"):
                view = AddSessionView()
                view._open_session(title)
                self.send_patch(view, initial=True)
                terrain, _, elevation, _, movement, secondary = view.content.controls[2:8]

                def choose(selector, value):
                    patch_dataclass(selector.content, {"selected": [value] if value else []})
                    with patch.object(
                        ft.SegmentedButton, "update",
                        side_effect=lambda: self.send_patch(selector.content),
                    ):
                        selector.content.on_change(SimpleNamespace(control=selector.content))
                    self.send_patch(view)

                self.assertFalse(secondary.visible)
                self.assertIsNone(secondary.content)
                for terrain_value in ("road", "rolling", "technical", "treadmill"):
                    choose(terrain, terrain_value)
                    self.assertFalse(secondary.visible)
                    self.assertIsNone(secondary.content)
                    for elevation_value in ("flat", "hilly"):
                        choose(elevation, elevation_value)
                        if terrain_value == "treadmill" and elevation_value == "hilly":
                            self.assertFalse(secondary.visible)
                            self.assertIsNone(secondary.content)
                            for movement_value in ("walk", "run"):
                                choose(movement, movement_value)
                                self.assertTrue(secondary.visible)
                                self.assert_secondary_fields(
                                    secondary.content, title, terrain_value, elevation_value,
                                )
                            choose(movement, None)
                            self.assertFalse(secondary.visible)
                            choose(movement, "run")
                        self.assertTrue(secondary.visible)
                        self.assert_secondary_fields(
                            secondary.content, title, terrain_value, elevation_value,
                        )

                # Changing the slope recomputes the required fields.
                choose(elevation, "flat")
                self.assertTrue(secondary.visible)
                self.assert_secondary_fields(secondary.content, title, "treadmill", "flat")
                choose(elevation, "hilly")
                self.assertIsNone(movement.selected)
                self.assertFalse(secondary.visible)
                choose(movement, "run")
                choose(terrain, "road")
                self.assertFalse(secondary.visible)
                self.assertIsNone(secondary.content)
                choose(elevation, "hilly")
                self.assertTrue(secondary.visible)
                self.assert_secondary_fields(secondary.content, title, "road", "hilly")
                choose(elevation, None)
                self.assertFalse(secondary.visible)

                view._back_to_choices()
                view._open_session(title)
                self.assertFalse(view.content.controls[7].visible)
                self.assertIsNone(view.content.controls[7].content)

    def test_threshold_format_follows_required_choices_and_resets_on_upstream_changes(self):
        self.check_format_selector(
            "Seuil", ThresholdFormatSelector, "Format seuil",
            ["Continu", "3 répétitions"], ("continuous", "three_repetitions"),
        )

    def test_vo2max_format_follows_required_choices_and_resets_on_upstream_changes(self):
        self.check_format_selector(
            "VO2max", VO2maxFormatSelector, "Format VO2max",
            ["4 répétitions", "5 répétitions", "6 répétitions"],
            ("four_repetitions", "five_repetitions", "six_repetitions"),
        )

    def check_format_selector(self, title, selector_class, heading_text, labels, values):
        with patch.object(AddSessionView, "update"):
            view = AddSessionView()
            view._open_session(title)
            self.send_patch(view, initial=True)
            terrain, _, slope, _, movement, heading, selector, secondary = view.content.controls[2:10]
            self.assertIsInstance(selector, selector_class)
            self.assertEqual(heading.value, heading_text)
            self.assertFalse(heading.visible)
            self.assertFalse(selector.visible)
            self.assertFalse(secondary.visible)
            self.assertEqual(
                [segment.label.content.controls[1].value for segment in selector.content.segments],
                labels,
            )
            if title == "VO2max":
                icons = [s.label.content.controls[0] for s in selector.content.segments]
                self.assertTrue(all(isinstance(icon, ft.Text) for icon in icons))
                self.assertEqual([icon.value for icon in icons], ["x4", "x5", "x6"])

            def choose(component, value):
                patch_dataclass(component.content, {"selected": [value] if value else []})
                with patch.object(
                    ft.SegmentedButton, "update",
                    side_effect=lambda: self.send_patch(component.content),
                ):
                    component.content.on_change(SimpleNamespace(control=component.content))
                return self.send_patch(view)

            def check_formats():
                self.assertTrue(heading.visible)
                self.assertTrue(selector.visible)
                self.assertIsNone(selector.selected)
                self.assertFalse(secondary.visible)
                for value in values:
                    choose(selector, value)
                    self.assertEqual(selector.selected, value)
                    self.assertFalse(selector.content.allow_empty_selection)
                    self.assertFalse(selector.content.allow_multiple_selection)
                    self.assertTrue(secondary.visible)
                    self.assert_secondary_fields(
                        secondary.content, title, terrain.selected, slope.selected, value,
                    )
                    numeric_fields = [
                        c for c in secondary.content.controls
                        if isinstance(c, NumericInput) and not isinstance(c, ZoneDurationInput)
                    ]
                    self.assertTrue(all(c.value is None for c in numeric_fields))
                    # Each phase has independent duration and speed values.
                    with patch.object(NumericInput, "update"):
                        expected = [
                            Decimal("5.5") if isinstance(field, RPEInput) else Decimal(index)
                            for index, field in enumerate(numeric_fields, start=1)
                        ]
                        for field, value in zip(numeric_fields, expected, strict=True):
                            field._field.value = str(value)
                            field._field.on_change(SimpleNamespace(control=field._field))
                        self.assertEqual(
                            [field.value for field in numeric_fields],
                            expected,
                        )
                choose(selector, None)
                self.assertFalse(secondary.visible)
                choose(selector, values[0])

            for terrain_value in ("road", "rolling", "technical", "treadmill"):
                choose(terrain, terrain_value)
                self.assertFalse(selector.visible)
                self.assertFalse(heading.visible)
                self.assertIsNone(selector.selected)
                for slope_value in ("flat", "hilly"):
                    choose(slope, slope_value)
                    if terrain_value == "treadmill" and slope_value == "hilly":
                        self.assertFalse(selector.visible)
                        for movement_value in ("walk", "run"):
                            choose(movement, movement_value)
                            check_formats()
                    else:
                        check_formats()

            message = choose(slope, "flat")
            self.assertTrue(selector.visible)
            self.assertIsNone(selector.selected)
            self.assertFalse(secondary.visible)
            self.assertTrue(any(
                len(op) == 4 and op[2] == "selected" and op[3] == []
                for op in message[1:]
            ), message)
            choose(selector, values[-1])
            choose(terrain, "road")
            self.assertFalse(selector.visible)
            self.assertIsNone(selector.selected)
            self.assertFalse(secondary.visible)
            view._back_to_choices()
            view._open_session(title)
            self.assertFalse(view.content.controls[8].visible)
            self.assertIsNone(view.content.controls[8].selected)

    def test_weather_and_comments_support_client_input(self):
        weather = WeatherSelector()
        self.send_patch(weather, initial=True)
        self.assertIsNone(weather.selected)
        self.assertEqual(
            [s.label.content.controls[1].value for s in weather._selector.segments],
            ["Normale", "Vent", "Pluie", "Vent & Pluie"],
        )
        for value in ("normal", "wind", "rain", "wind_rain"):
            patch_dataclass(weather._selector, {"selected": [value]})
            with patch.object(ft.SegmentedButton, "update"):
                weather._selector.on_change(SimpleNamespace(control=weather._selector))
            self.assertEqual(weather.selected, value)
            self.assertFalse(weather._selector.allow_empty_selection)
            self.assertFalse(weather._selector.allow_multiple_selection)

        comments = CommentsInput()
        self.send_patch(comments, initial=True)
        self.assertEqual(comments.value, "")
        text = "Séance difficile\nVent & pluie, puis éclaircies."
        patch_dataclass(comments._field, {"value": text})
        with patch.object(ft.TextField, "update"):
            comments._field.on_change(SimpleNamespace(control=comments._field))
        self.assertEqual(comments.value, text)



    def test_date_picker_defaults_to_today_and_displays_confirmed_date(self):
        selector = DateSelector()
        self.assertEqual(selector.selected, date.today())
        self.assertEqual(selector._date_text.value, date.today().strftime("%d/%m/%Y"))
        page = Mock()
        with patch.object(DateSelector, "page", new_callable=PropertyMock, return_value=page):
            selector.content.controls[1].on_click(SimpleNamespace())
        picker = page.show_dialog.call_args.args[0]
        self.assertIsInstance(picker, ft.DatePicker)
        self.assertEqual(picker.value, date.today())
        self.assertEqual(picker.last_date, date.today())
        # Dates without a time avoid UTC conversion when opening the picker.
        self.assertNotIsInstance(picker.value, datetime)
        self.assertNotIsInstance(picker.last_date, datetime)
        chosen = date.today() - timedelta(days=3)
        picker.value = datetime(chosen.year, chosen.month, chosen.day)
        with patch.object(DateSelector, "update"):
            picker.on_change(SimpleNamespace(control=picker))
            self.assertEqual(selector.selected, chosen)
            self.assertEqual(selector._date_text.value, chosen.strftime("%d/%m/%Y"))
            picker.value = None
            picker.on_change(SimpleNamespace(control=picker))
            self.assertEqual(selector.selected, chosen)

    def test_running_views_preserve_main_and_secondary_forms_across_tabs(self):
        with patch.object(AddSessionView, "update"):
            page = Mock()
            with patch("trail_mania.app.initialize_database"):
                create_app(page)
            container = page.add.call_args.args[0].content
            nav = page.navigation_bar

            def select_tab(index):
                nav.selected_index = index
                nav.on_change(SimpleNamespace(control=nav))

            select_tab(3)
            view = container.content
            for title, _ in SESSION_OPTIONS[:-1]:
                with self.subTest(title=title):
                    view._open_session(title)
                    self.assertEqual(len(view.content.controls), 10 if title in ("Seuil", "VO2max") else 8)
                    terrain, _, elevation, _, movement = view.content.controls[2:7]

                    def choose(component, value):
                        patch_dataclass(component.content, {"selected": [value]})
                        with patch.object(ft.SegmentedButton, "update"):
                            component.content.on_change(SimpleNamespace(control=component.content))

                    choose(terrain, "treadmill")
                    choose(elevation, "hilly")
                    choose(movement, "run")
                    if title in ("Seuil", "VO2max"):
                        format_selector = view.content.controls[8]
                        format_value = "three_repetitions" if title == "Seuil" else "five_repetitions"
                        choose(format_selector, format_value)
                    secondary = view.content.controls[-1]
                    self.assertTrue(secondary.visible)
                    form = secondary.content
                    session_date, first_numeric = form.controls[:2]
                    comments = form.controls[-2]
                    selected_date = date.today() - timedelta(days=2)
                    with patch.object(DateSelector, "update"):
                        session_date._change_date(SimpleNamespace(
                            control=SimpleNamespace(value=selected_date),
                        ))
                    first_numeric._field.value = "12,5"
                    with patch.object(NumericInput, "update"):
                        first_numeric._field.on_change(SimpleNamespace(control=first_numeric._field))
                    patch_dataclass(comments._field, {"value": "Bonne séance"})
                    with patch.object(ft.TextField, "update"):
                        comments._field.on_change(SimpleNamespace(control=comments._field))
                    zones = [c for c in form.controls if isinstance(c, ZoneDurationInput)]
                    heart_fields = [c for c in form.controls if isinstance(c, HeartRateInput)]
                    with patch.object(NumericInput, "update"):
                        for index, zone in enumerate(zones, start=1):
                            zone._field.value = f"00:01:{index:02d}"
                            zone._field.on_change(SimpleNamespace(control=zone._field))
                        for index, heart in enumerate(heart_fields, start=130):
                            heart._field.value = str(index)
                            heart._field.on_change(SimpleNamespace(control=heart._field))
                    for index in (0, 1, 2):
                        select_tab(index)
                        select_tab(3)
                        self.assertIs(container.content, view)
                        self.assertEqual(terrain.selected, "treadmill")
                        self.assertEqual(elevation.selected, "hilly")
                        self.assertEqual(movement.selected, "run")
                        self.assertIs(view.content.controls[-1], secondary)
                        self.assertTrue(secondary.visible)
                        self.assertIs(secondary.content, form)
                        self.assert_secondary_fields(
                            form, title, "treadmill", "hilly",
                            format_value if title in ("Seuil", "VO2max") else None,
                        )
                        if title in ("Seuil", "VO2max"):
                            self.assertEqual(format_selector.selected, format_value)
                        self.assertEqual(session_date.selected, selected_date)
                        self.assertEqual(first_numeric.value, Decimal("12.5"))
                        self.assertEqual(comments.value, "Bonne séance")
                        self.assertEqual([zone.value for zone in zones], [61, 62, 63, 64, 65])
                        self.assertEqual(
                            [heart.value for heart in heart_fields],
                            [Decimal(index) for index in range(130, 130 + len(heart_fields))],
                        )
                    view._back_to_choices()
                    view._open_session(title)
                    terrain, _, elevation, _, movement = view.content.controls[2:7]
                    self.assertIsNone(terrain.selected)
                    self.assertIsNone(elevation.selected)
                    self.assertIsNone(movement.selected)

    def test_calendar_utc_midnight_is_displayed_as_the_local_day(self):
        for offset, selected_day in ((1, date(2026, 1, 10)), (2, date(2026, 7, 10))):
            with self.subTest(offset=offset):
                local_timezone = timezone(timedelta(hours=offset))

                class LocalDateTime(datetime):
                    def astimezone(self, tz=None):
                        return super().astimezone(tz or local_timezone)

                # Central European midnight falls on the previous day in the UTC protocol.
                midnight = datetime(
                    selected_day.year, selected_day.month, selected_day.day,
                    tzinfo=local_timezone,
                ).astimezone(timezone.utc)
                payload = LocalDateTime.fromisoformat(midnight.isoformat())
                selector = DateSelector()
                with patch.object(DateSelector, "update"):
                    selector._change_date(SimpleNamespace(control=SimpleNamespace(value=payload)))
                self.assertEqual(selector.selected, selected_day)
                self.assertEqual(selector._date_text.value, selected_day.strftime("%d/%m/%Y"))

    def test_future_dates_are_rejected_and_today_is_allowed(self):
        selector = DateSelector()
        original = selector.selected
        for future in (
            date.today() + timedelta(days=1),
            datetime.combine(date.today() + timedelta(days=30), datetime.min.time()),
        ):
            control = SimpleNamespace(value=future)
            with patch.object(DateSelector, "update") as update:
                selector._change_date(SimpleNamespace(control=control))
                update.assert_not_called()
            self.assertEqual(selector.selected, original)
            self.assertEqual(control.value, original)
        with patch.object(DateSelector, "update"):
            selector._change_date(SimpleNamespace(control=SimpleNamespace(value=date.today())))
        self.assertEqual(selector.selected, date.today())

    def test_choices_start_empty_then_disallow_clearing_the_active_choice(self):
        with patch.object(AddSessionView, "update"):
            view = AddSessionView()
            view._open_session("Seuil")
            self.send_patch(view, initial=True)
            terrain, _, elevation, _, movement = view.content.controls[2:7]

            def choose(selector, value):
                messages = []
                patch_dataclass(selector.content, {"selected": [value]})
                with patch.object(
                    ft.SegmentedButton,
                    "update",
                    side_effect=lambda: messages.append(self.send_patch(selector.content)),
                ):
                    selector.content.on_change(SimpleNamespace(control=selector.content))
                messages.append(self.send_patch(view))
                return [op for message in messages for op in message[1:]]

            for selector, value in (
                (terrain, "treadmill"), (elevation, "hilly"), (movement, "walk")
            ):
                self.assertIsNone(selector.selected)
                self.assertTrue(selector.content.allow_empty_selection)
                operations = choose(selector, value)
                self.assertEqual(selector.selected, value)
                self.assertFalse(selector.content.allow_empty_selection)
                self.assertFalse(selector.content.allow_multiple_selection)
                self.assertTrue(any(
                    len(op) == 4 and op[2] == "allow_empty_selection" and op[3] is False
                    for op in operations
                ), operations)

            # Another option can still replace the active choice.
            choose(movement, "run")
            self.assertEqual(movement.selected, "run")
            choose(terrain, "road")
            for selector in (elevation, movement):
                self.assertIsNone(selector.selected)
                self.assertTrue(selector.content.allow_empty_selection)

            view._back_to_choices()
            view._open_session("Seuil")
            terrain, _, elevation, _, movement = view.content.controls[2:7]
            for selector in (terrain, elevation, movement):
                self.assertIsNone(selector.selected)
                self.assertTrue(selector.content.allow_empty_selection)


if __name__ == "__main__":
    unittest.main()
