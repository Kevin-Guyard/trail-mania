import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import msgpack
import flet as ft
from flet.controls.base_control import BaseControl
from flet.messaging.protocol import configure_encode_object_for_msgpack

from trail_mania.components import (
    DistanceInput, DurationInput, ElevationInput, HeartRateInput, InclinationInput, RPEInput, SpeedInput, TemperatureInput,
)
from trail_mania.components.numeric_input import NumericInput


class NumericInputTest(unittest.TestCase):
    classes = (DistanceInput, DurationInput, SpeedInput, TemperatureInput, RPEInput, InclinationInput, ElevationInput, HeartRateInput)

    def enter(self, component, value, commit=True):
        component._field.value = value
        event = SimpleNamespace(control=component._field)
        with patch.object(NumericInput, "update"):
            handler = component._field.on_submit if commit else component._field.on_change
            handler(event)

    def click(self, component, direction):
        row = component.content.controls[1].content
        button = row.controls[2 if direction == 1 else 0]
        with patch.object(NumericInput, "update"):
            button.on_tap(SimpleNamespace(control=button))

    def test_component_defaults_and_flet_serialization(self):
        for cls in self.classes:
            with self.subTest(component=cls.__name__):
                component = cls()
                if cls in (InclinationInput, ElevationInput):
                    self.assertEqual(component.value, Decimal("0"))
                    self.assertEqual(component._field.value, "0" if cls is ElevationInput else "0,0")
                else:
                    self.assertIsNone(component.value)
                    self.assertEqual(component._field.value, "")
                self.assertEqual(component._field.keyboard_type, ft.KeyboardType.NUMBER)
                # Les paramètres Decimal restent côté Python, hors protocole UI.
                msgpack.packb(
                    component, default=configure_encode_object_for_msgpack(BaseControl)
                )

    def test_units_and_precision(self):
        for cls, unit, typed, shown in (
            (DistanceInput, "km", "12.34", "12,3"),
            (DurationInput, "min", "12.26", "12,5"),
            (SpeedInput, "km/h", "10,26", "10,3"),
            (TemperatureInput, "°C", "-2,5", "-3"),
            (RPEInput, "", "6.74", "6,5"),
            (InclinationInput, "%", "4.76", "5,0"),
            (ElevationInput, "m", "123,6", "124"),
            (HeartRateInput, "bpm", "150", "150"),
        ):
            with self.subTest(component=cls.__name__):
                component = cls()
                self.enter(component, typed)
                unit_control = component.content.controls[1].content.controls[1].controls[1]
                self.assertEqual(unit_control.content.value, unit)
                self.assertEqual(component._field.value, shown)
                self.assertEqual(component.value, Decimal(shown.replace(",", ".")))

    def test_increment_and_decrement_keep_exact_steps(self):
        for cls in self.classes:
            with self.subTest(component=cls.__name__):
                component = cls()
                for _ in range(7):
                    self.click(component, 1)
                self.assertEqual(component.value, 7 * component.step)
                for _ in range(3):
                    self.click(component, -1)
                self.assertEqual(component.value, 4 * component.step)

    def test_negative_values_and_lower_bounds(self):
        for cls in (DistanceInput, DurationInput, SpeedInput, RPEInput, ElevationInput, HeartRateInput, InclinationInput):
            component = cls()
            self.click(component, -1)
            self.assertEqual(component.value, component.minimum)
            self.enter(component, "-1")
            self.assertIsNone(component.value)
            self.assertIsNotNone(component._field.error)
        for cls, expected in ((TemperatureInput, "-1"),):
            component = cls()
            self.click(component, -1)
            self.assertEqual(component.value, Decimal(expected))

    def test_invalid_input_and_clearing(self):
        for cls in self.classes:
            for text in ("abc", "NaN", "Infinity", "1,2.3"):
                component = cls()
                self.enter(component, text)
                self.assertIsNone(component.value)
                self.assertIsNotNone(component._field.error)
                self.enter(component, "2")
                self.assertIsNone(component._field.error)
                self.enter(component, "")
                self.assertIsNone(component.value)
                self.assertEqual(component._field.value, "")

    def test_heart_rate_inclusive_maximum_for_input_and_buttons(self):
        component = HeartRateInput()
        for commit in (False, True):
            for text in ("219", "220"):
                self.enter(component, text, commit=commit)
                self.assertEqual(component.value, Decimal(text))
                self.assertIsNone(component._field.error)
            for text in ("221", "999", "220.1"):
                self.enter(component, text, commit=commit)
                self.assertIsNone(component.value)
                self.assertEqual(component._field.error, "Saisir un nombre entre 0 et 220")
        self.enter(component, "219")
        self.click(component, 1)
        self.assertEqual(component.value, Decimal("220"))
        self.click(component, 1)
        self.assertEqual(component.value, Decimal("220"))
        self.assertEqual(component._field.value, "220")
        self.click(component, -1)
        self.assertEqual(component.value, Decimal("219"))

    def test_editing_does_not_reformat_before_blur(self):
        component = DistanceInput()
        self.enter(component, "12,", commit=False)
        self.assertEqual(component._field.value, "12,")
        component._field.value = "12,35"
        with patch.object(NumericInput, "update"):
            component._field.on_blur(SimpleNamespace(control=component._field))
        self.assertEqual(component._field.value, "12,4")

    def test_inclination_maximum_applies_to_typing_and_buttons(self):
        component = InclinationInput()
        for commit in (False, True):
            self.enter(component, "99,5", commit=commit)
            self.assertEqual(component.value, Decimal("99.5"))
            self.click(component, 1)
            self.assertEqual(component.value, Decimal("99.5"))
            for text in ("99,6", "100"):
                self.enter(component, text, commit=commit)
                self.assertIsNone(component.value)
                self.assertIsNotNone(component._field.error)


if __name__ == "__main__":
    unittest.main()
