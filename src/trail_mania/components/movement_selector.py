"""Single-choice walking or running selection for inclined treadmills."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import ChoiceSelector, selector_segment
from trail_mania.session_types import Movement


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
            selector_segment(movement, movement.label, icon)
            for movement, icon in (
                (Movement.WALK, ft.Icons.DIRECTIONS_WALK),
                (Movement.RUN, ft.Icons.DIRECTIONS_RUN),
            )
        ]
