"""Single-choice walking or running selection for inclined treadmills."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import (
    ChoiceSelector,
    selector_icon,
    selector_segment,
)
from trail_mania.session_types import Movement


def movement_icon(movement: Movement) -> ft.Icon:
    """Build the movement pictogram shared by selectors and table cells.

    Parameters
    ----------
    movement : Movement
        Walking or running choice to represent.

    Returns
    -------
    ft.Icon
        Fresh black movement icon with the canonical French tooltip and
        accessibility label.
    """
    icon = ft.Icons.DIRECTIONS_WALK if movement == Movement.WALK else ft.Icons.DIRECTIONS_RUN
    return selector_icon(icon, movement.label)


@ft.control
class MovementSelector(ChoiceSelector):
    """Select walking or running on an inclined treadmill.

    Notes
    -----
    Inherits the initially empty, single-choice behavior and on_change
    callback from ChoiceSelector. Selected values are stable keys:
    walk and run.
    """

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build the selector's options in display order.

        Returns
        -------
        list of ft.Segment
            Fresh, labeled segments using the shared session-choice keys.
        """
        return [
            selector_segment(movement, movement.label, movement_icon(movement))
            for movement in Movement
        ]
