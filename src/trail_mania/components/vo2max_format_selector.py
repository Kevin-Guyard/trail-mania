"""Selection of supported VO2max repetition counts."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import ChoiceSelector, selector_segment
from trail_mania.session_types import SESSION_FORMATS, SessionType


@ft.control
class VO2maxFormatSelector(ChoiceSelector):
    """Select four, five or six VO2max repetitions.

    Notes
    -----
    Inherits the initially empty, single-choice behavior and on_change
    callback from ChoiceSelector. Selected values are stable keys:
    four_repetitions, five_repetitions and six_repetitions.
    """

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build the selector's options in display order.

        Returns
        -------
        list of ft.Segment
            Fresh, labeled segments using the shared session-choice keys.
        """
        return [
            selector_segment(
                session_format,
                session_format.label,
                ft.Text(
                    f"x{session_format.repetitions}",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLACK,
                ),
            )
            for session_format in SESSION_FORMATS[SessionType.VO2MAX]
        ]
