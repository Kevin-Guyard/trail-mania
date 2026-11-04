"""Coordinate calendar swipes and reject events from inactive period grids."""

from collections.abc import Callable
from typing import Final, Self

import flet as ft


_PAGE_OFFSETS: Final[tuple[int, int, int]] = (-1, 0, 1)
_SWIPE_THRESHOLD: Final[int] = 50
_SWIPE_ANIMATION_DURATION: Final[int] = 180


class CalendarPager:
    """Manage horizontal swipes between three grids independently of their dates.

    Parameters
    ----------
    calendars : tuple of (ft.Control, ft.Control, ft.Control)
        Previous, current, and next calendar grids, in that order.
    spacing : float
        Gap between adjacent grids, in pixels.
    viewport_width : float
        Last measured viewport width, in pixels. Zero means it is not yet known.
    on_change : callable
        Receive -1 or 1 when a transition to a neighboring grid completes.
    on_update : callable
        Refresh the owning view after grid offsets or animations change.

    Attributes
    ----------
    control : ft.GestureDetector
        Gesture detector wrapping the clipped calendar grids.
    viewport_width : float
        Most recent positive viewport width, reused when replacing the pager.

    Notes
    -----
    A horizontal drag of at least 50 pixels changes one period if its horizontal
    distance exceeds its vertical distance. Other drags return to the current
    grid. Settling uses a 180 ms ease-out animation.
    """

    def __init__(
        self: Self,
        calendars: tuple[ft.Control, ft.Control, ft.Control],
        *,
        spacing: float,
        viewport_width: float,
        on_change: Callable[[int], None],
        on_update: Callable[[], None],
    ) -> None:
        """Initialize gesture state and wrap the three supplied calendar grids.

        Notes
        -----
        Constructor parameters are documented on the class. Existing grids
        are mounted into the pager without rebuilding them or querying data.
        The owner installs ``control`` and sends the initial client update.
        """
        self.viewport_width: float = viewport_width
        self._spacing: float = spacing
        self._on_change: Callable[[int], None] = on_change
        self._on_update: Callable[[], None] = on_update
        self._active: bool = True
        self._swipe_start: ft.Offset | None = None
        self._swipe_progress: float = 0.0
        # None: idle or dragging; 0: snap back; -1/+1: change the period.
        self._swipe_target: int | None = None
        self._pages: list[ft.Container] = [
            ft.Container(
                offset=ft.Offset(offset, 0),
                # Keep the same animation widget during dragging and settling.
                animate_offset=ft.Animation(0),
                content=calendar,
            )
            for offset, calendar in zip(_PAGE_OFFSETS, calendars)
        ]
        self._set_progress(0)
        self.control: ft.GestureDetector = ft.GestureDetector(
            expand=True,
            drag_interval=16,
            on_size_change=self._resize_viewport,
            on_horizontal_drag_start=self._start_swipe,
            on_horizontal_drag_update=self._update_swipe,
            on_horizontal_drag_end=self._end_swipe,
            # Clipping the Stack alone does not hide offset-transformed content.
            content=ft.Container(
                border_radius=ft.BorderRadius.all(0),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Stack(
                    fit=ft.StackFit.EXPAND,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    controls=self._pages,
                ),
            ),
        )

    def deactivate(self: Self) -> None:
        """Stop accepting events while a detail is open or the pager is replaced.

        Notes
        -----
        Gesture, resize and animation-completion handlers check this flag
        before changing offsets or requesting another period. Deactivation
        does not mutate the grids or send an update; returning to the calendar
        constructs a fresh active pager.
        """
        self._active = False

    def _resize_viewport(
        self: Self, event: ft.LayoutSizeChangeEvent[ft.GestureDetector]
    ) -> None:
        """Update grid offsets when the active viewport width changes.

        Parameters
        ----------
        event : ft.LayoutSizeChangeEvent[ft.GestureDetector]
            Size event providing the viewport width in pixels.
        """
        if not self._active or event.control is not self.control:
            return
        if event.width > 0 and event.width != self.viewport_width:
            self.viewport_width = event.width
            self._set_progress(self._swipe_progress)
            self._on_update()

    def _set_progress(self: Self, progress: float) -> None:
        """Position all three grids at a clamped swipe displacement.

        Parameters
        ----------
        progress : float
            Page-relative displacement, clamped to [-1, 1]. Positive values
            reveal the previous grid; negative values reveal the next grid.
        """
        self._swipe_progress = max(-1.0, min(1.0, progress))
        # Offsets are relative to width: preserve the cell spacing between grids
        # regardless of the available viewport width.
        stride = 1 + self._spacing / self.viewport_width if self.viewport_width > 0 else 1
        for offset, page in zip(_PAGE_OFFSETS, self._pages):
            page.offset = ft.Offset((offset + self._swipe_progress) * stride, 0)

    def _start_swipe(self: Self, event: ft.DragStartEvent[ft.GestureDetector]) -> None:
        """Record a drag origin when the measured pager is ready for a gesture.

        Parameters
        ----------
        event : ft.DragStartEvent[ft.GestureDetector]
            Horizontal drag event carrying the local pointer position.

        Notes
        -----
        New gestures are ignored while a settling transition is pending.
        """
        if not self._active or event.control is not self.control:
            return
        if self._swipe_target is None and self.viewport_width > 0:
            self._swipe_start = event.local_position

    def _update_swipe(self: Self, event: ft.DragUpdateEvent[ft.GestureDetector]) -> None:
        """Move the grids to follow the pointer during an active drag.

        Parameters
        ----------
        event : ft.DragUpdateEvent[ft.GestureDetector]
            Horizontal drag update carrying the local pointer position.
        """
        if not self._active or event.control is not self.control or self._swipe_start is None:
            return
        delta_x = event.local_position.x - self._swipe_start.x
        self._set_progress(delta_x / (self.viewport_width + self._spacing))
        self._on_update()

    def _end_swipe(self: Self, event: ft.DragEndEvent[ft.GestureDetector]) -> None:
        """Resolve the gesture and settle on the current or a neighboring grid.

        Parameters
        ----------
        event : ft.DragEndEvent[ft.GestureDetector]
            Drag end event used to compare horizontal and vertical distances.
        """
        if not self._active or event.control is not self.control:
            return
        start = self._swipe_start
        self._swipe_start = None
        if start is None:
            return

        delta_x = event.local_position.x - start.x
        delta_y = event.local_position.y - start.y
        target = 0
        if abs(delta_x) >= _SWIPE_THRESHOLD and abs(delta_x) > abs(delta_y):
            target = 1 if delta_x < 0 else -1

        # Commit the selected period only after the incoming grid has settled.
        self._swipe_target = target
        if self._swipe_progress == -target:
            self._finish_swipe()
            return
        for page in self._pages:
            page.animate_offset = ft.Animation(
                _SWIPE_ANIMATION_DURATION, ft.AnimationCurve.EASE_OUT
            )
        self._pages[1].on_animation_end = self._finish_swipe
        self._set_progress(-target)
        self._on_update()

    def _finish_swipe(self: Self, event: ft.Event[ft.Container] | None = None) -> None:
        """Complete a pending transition and apply any requested period change.

        Parameters
        ----------
        event : ft.Event[ft.Container] or None, optional
            Animation completion event from the current grid's container.
            None completes the transition directly when its target offset
            has already been reached. Defaults to None.
        """
        if not self._active or (event is not None and event.control is not self._pages[1]):
            return
        target = self._swipe_target
        if target is None:
            return
        self._swipe_target = None
        if target:
            self._on_change(target)
        else:
            for page in self._pages:
                page.animate_offset = ft.Animation(0)
            self._pages[1].on_animation_end = None
            self._on_update()
