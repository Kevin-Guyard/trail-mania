import unittest
from types import SimpleNamespace
from unittest.mock import patch

import msgpack
from flet.controls.base_control import BaseControl
from flet.messaging.protocol import configure_encode_object_for_msgpack

from trail_mania.components import ZoneDurationInput
from trail_mania.components.numeric_input import NumericInput


class ZoneDurationInputTest(unittest.TestCase):
    def enter(self, component, text, commit=False):
        component._field.value = text
        with patch.object(NumericInput, "update"):
            handler = component._field.on_blur if commit else component._field.on_change
            handler(SimpleNamespace(control=component._field))

    def click(self, component, direction):
        buttons = component.content.controls[1].content.controls
        with patch.object(NumericInput, "update"):
            buttons[2 if direction == 1 else 0].on_click(SimpleNamespace())

    def test_starts_at_zero_and_serializes(self):
        component = ZoneDurationInput(label="Z1")
        self.assertEqual(component.label, "Z1")
        self.assertEqual(component._field.hint_text, "00:00:00")
        self.assertEqual(component._field.value, "00:00:00")
        self.assertEqual(component.value, 0)
        msgpack.packb(component, default=configure_encode_object_for_msgpack(BaseControl))

    def test_time_input_returns_seconds(self):
        component = ZoneDurationInput()
        for text, seconds in (("00:00:00", 0), ("01:02:03", 3723), ("100:00:01", 360001)):
            with self.subTest(text=text):
                self.enter(component, text, commit=True)
                self.assertEqual(component.value, seconds)
                self.assertEqual(component._field.value, text)
                self.assertIsNone(component._field.error)

    def test_buttons_adjust_one_second_and_carry_minutes_and_hours(self):
        component = ZoneDurationInput()
        self.click(component, 1)
        self.assertEqual(component._field.value, "00:00:01")
        for before, after in (("00:00:59", "00:01:00"), ("00:59:59", "01:00:00")):
            self.enter(component, before)
            seconds = component.value
            self.click(component, 1)
            self.assertEqual(component.value, seconds + 1)
            self.assertEqual(component._field.value, after)
            self.click(component, -1)
            self.assertEqual(component._field.value, before)
        self.enter(component, "00:00:00")
        self.click(component, -1)
        self.assertEqual(component.value, 0)
        self.assertEqual(component._field.value, "00:00:00")

    def test_invalid_times_and_clearing(self):
        component = ZoneDurationInput()
        for text in ("-01:00:00", "00:60:00", "00:00:60", "01:02", "1:02:03", "1.5", "abc"):
            with self.subTest(text=text):
                self.enter(component, text)
                self.assertIsNone(component.value)
                self.assertIsNotNone(component._field.error)
                self.enter(component, "00:01:00")
                self.assertEqual(component.value, 60)
                self.assertIsNone(component._field.error)
        self.enter(component, "")
        self.assertIsNone(component.value)
        self.assertIsNone(component._field.error)


if __name__ == "__main__":
    unittest.main()
