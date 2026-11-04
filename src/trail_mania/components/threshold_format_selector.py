"""Selection of continuous or repeated threshold-session formats."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import ChoiceSelector, selector_segment
from trail_mania.session_types import SessionFormat


@ft.control
class ThresholdFormatSelector(ChoiceSelector):
    """Select a continuous threshold effort or three repetitions.

    Notes
    -----
    Inherits the initially empty, single-choice behavior and on_change
    callback from ChoiceSelector. Selected values are stable keys:
    continuous and three_repetitions.
    """

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build the selector's options in display order.

        Returns
        -------
        list of ft.Segment
            Fresh, labeled segments using the shared session-choice keys.
        """
        return [
            selector_segment(session_format, session_format.label, icon)
            for session_format, icon in (
                (SessionFormat.CONTINUOUS, ft.Icons.ARROW_FORWARD),
                (SessionFormat.THREE_REPETITIONS, ft.Icons.REPEAT),
            )
        ]
