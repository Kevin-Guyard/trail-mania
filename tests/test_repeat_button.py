import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from trail_mania.components import DistanceInput, InclinationInput, ZoneDurationInput
from trail_mania.components.numeric_input import NumericInput
from trail_mania.components.repeat_button import RepeatButton


class RepeatButtonTest(unittest.IsolatedAsyncioTestCase):
    async def run_ticks(self, button, count):
        """Run the real repetition loop with a deterministic advancing clock."""
        now = 0.0
        deadlines = []

        async def sleep(delay):
            nonlocal now
            if len(deadlines) == count:
                raise asyncio.CancelledError
            now += delay
            deadlines.append(now)

        timer = SimpleNamespace(
            get_running_loop=lambda: SimpleNamespace(time=lambda: now),
            sleep=sleep,
        )
        with patch("trail_mania.components.repeat_button.asyncio", timer):
            with self.assertRaises(asyncio.CancelledError):
                await button._repeat()
        return deadlines

    async def test_accelerates_at_one_and_two_seconds(self):
        step = Mock()
        button = RepeatButton(on_step=step)
        deadlines = await self.run_ticks(button, 28)
        expected = (
            [i / 3 for i in range(1, 4)]
            + [1 + i / 5 for i in range(1, 6)]
            + [2 + i / 10 for i in range(1, 21)]
        )
        for actual, wanted in zip(deadlines, expected, strict=True):
            self.assertAlmostEqual(actual, wanted)
        self.assertEqual(step.call_count, 28)
        button.on_tap(SimpleNamespace())
        self.assertEqual(step.call_count, 28)  # No extra step on release.

    async def test_short_press_emits_exactly_one_step(self):
        step = Mock()
        button = RepeatButton(on_step=step)
        await button.on_tap_down(SimpleNamespace())
        task = button._task
        await button.on_tap_up(SimpleNamespace())
        button.on_tap(SimpleNamespace())
        with self.assertRaises(asyncio.CancelledError):
            await task
        step.assert_called_once()

    async def test_release_cancel_and_unmount_stop_repetition(self):
        for stop in ("release", "cancel", "unmount"):
            with self.subTest(stop=stop):
                step = Mock()
                button = RepeatButton(on_step=step)
                await button.on_tap_down(SimpleNamespace())
                task = button._task
                # Let the timer start waiting for its first deadline.
                await asyncio.sleep(0)
                if stop == "release":
                    await button.on_tap_up(SimpleNamespace())
                elif stop == "cancel":
                    await button.on_tap_cancel(SimpleNamespace())
                else:
                    button.will_unmount()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                step.assert_not_called()
                self.assertIsNone(button._task)

    async def test_repetition_preserves_steps_bounds_and_zone_carries(self):
        for component, start, direction, expected in (
            (DistanceInput(), Decimal("1"), 1, Decimal("2.8")),
            (DistanceInput(), Decimal("1"), -1, Decimal("0")),
            (InclinationInput(), Decimal("99"), 1, Decimal("99.5")),
            (ZoneDurationInput(), 3590, 1, 3608),
        ):
            with self.subTest(component=type(component).__name__, direction=direction):
                component.set_value(start)
                button = component.content.controls[1].content.controls[2 if direction == 1 else 0]
                with patch.object(NumericInput, "update"):
                    await self.run_ticks(button, 18)
                self.assertEqual(component.value, expected)


if __name__ == "__main__":
    unittest.main()
