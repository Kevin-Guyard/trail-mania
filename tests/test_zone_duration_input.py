import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft
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
            buttons[2 if direction == 1 else 0].on_tap(SimpleNamespace())

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


class SegmentedZoneDurationInputTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.component = ZoneDurationInput(label="Z1")
        self.enterContext(patch.object(NumericInput, "update"))

    async def edit(self, index, text):
        part = self.component._parts[index]
        part.value = text
        await part.on_change(SimpleNamespace(control=part))

    async def test_typing_advances_hours_then_minutes_then_seconds(self):
        hours, minutes, seconds = self.component._parts
        for part in (hours, minutes, seconds):
            self.assertEqual(part.keyboard_type, ft.KeyboardType.NUMBER)
            self.assertIsInstance(part.input_filter, ft.NumbersOnlyInputFilter)
        with patch.object(ft.TextField, "focus", new_callable=AsyncMock) as focus:
            await self.edit(0, "0")
            focus.assert_not_awaited()
            await self.edit(0, "02")
            self.assertEqual(focus.await_count, 1)
            await self.edit(1, "09")
            self.assertEqual(focus.await_count, 2)
            await self.edit(2, "15")
            self.assertEqual(focus.await_count, 2)
        self.assertEqual(self.component.value, 2 * 3600 + 9 * 60 + 15)

    async def test_single_digit_is_padded_when_leaving_each_group(self):
        component = self.component
        for index, text in enumerate(("2", "9", "3")):
            await self.edit(index, text)
            part = component._parts[index]
            self.assertEqual(part.value, text)
            part.on_blur(SimpleNamespace(control=part))
            self.assertEqual(part.value, text.zfill(2))
        self.assertEqual(component._field.value, "02:09:03")
        self.assertEqual(component.value, 7743)

    async def test_save_reads_uncommitted_segments_and_formats_them(self):
        component = self.component
        for part, value in zip(component._parts, ("100", "9", "1")):
            part.value = value
        self.assertEqual(component.pending_value, 360541)
        self.assertEqual(component._parts[1].value, "9")
        self.assertTrue(component.validate(required=True))
        self.assertEqual([part.value for part in component._parts], ["100", "09", "01"])
        self.assertEqual(component.value, 360541)

    async def test_invalid_segment_blocks_saving_and_shows_error(self):
        component = self.component
        await self.edit(1, "60")
        self.assertFalse(component.validate())
        self.assertIsNone(component.value)
        self.assertTrue(component._error_text.visible)
        await self.edit(1, "5")
        self.assertTrue(component.validate())
        self.assertFalse(component._error_text.visible)
        self.assertEqual(component.value, 300)

    async def test_submit_pads_group_and_focuses_next(self):
        part = self.component._parts[1]
        part.value = "9"
        with patch.object(ft.TextField, "focus", new_callable=AsyncMock) as focus:
            await part.on_submit(SimpleNamespace(control=part))
            focus.assert_awaited_once()
        self.assertEqual(part.value, "09")


if __name__ == "__main__":
    unittest.main()
