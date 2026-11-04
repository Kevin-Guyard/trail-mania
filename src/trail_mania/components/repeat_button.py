"""Numeric stepper button with accelerated repetition while held."""

import asyncio
from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft


@ft.control
class RepeatButton(ft.GestureDetector):
    """Emit one step on a tap, or 3, 5, then 10 steps/s while held.

    Seconds are counted from pointer-down. Release, gesture cancellation and
    removal from the view stop the timer. A held press adds no step on release.
    """

    icon: ft.IconData | None = None
    label: str = ""
    on_step: Callable[[], None] | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._repeated = False
        self.mouse_cursor = ft.MouseCursor.CLICK
        # One gesture recognizer owns the pointer, avoiding competition with
        # IconButton's tap recognizer. Keyboard activation remains available.
        self.content = ft.Container(
            ignore_interactions=True,
            content=ft.IconButton(
                icon=self.icon,
                icon_color=ft.Colors.BLACK,
                tooltip=self.label,
                on_click=self._tap,
            ),
        )
        self.on_tap_down = self._press
        self.on_tap_up = self._release
        self.on_tap_cancel = self._cancel
        self.on_tap = self._tap

    def _tap(self: Self, event: ft.Event) -> None:
        if not self._repeated and self.on_step is not None:
            self.on_step()
        self._repeated = False

    async def _press(self: Self, event: ft.Event) -> None:
        self._stop()
        self._repeated = False
        self._task = asyncio.create_task(self._repeat())

    async def _release(self: Self, event: ft.Event) -> None:
        self._stop()

    async def _cancel(self: Self, event: ft.Event) -> None:
        self._stop()
        self._repeated = False

    def _stop(self: Self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _repeat(self: Self) -> None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        tick = 1
        while True:
            # Absolute deadlines avoid accumulating drift between speed changes.
            if tick <= 3:
                deadline = tick / 3
            elif tick <= 8:
                deadline = 1 + (tick - 3) / 5
            else:
                deadline = 2 + (tick - 8) / 10
            await asyncio.sleep(max(0, started + deadline - loop.time()))
            self._repeated = True
            if self.on_step is not None:
                self.on_step()
            tick += 1

    def will_unmount(self: Self) -> None:
        self._stop()
        super().will_unmount()
