"""Single-choice selection of flat or hilly session profiles."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import ChoiceSelector, selector_segment
from trail_mania.session_types import Slope


@ft.control
class ElevationSelector(ChoiceSelector):
    """Select a flat or hilly route.

    Notes
    -----
    Inherits the initially empty, single-choice behavior and on_change
    callback from ChoiceSelector. Selected values are stable keys:
    flat and hilly.
    """

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build the selector's options in display order.

        Returns
        -------
        list of ft.Segment
            Fresh, labeled segments using the shared session-choice keys.
        """
        return [
            selector_segment(slope, slope.label, icon)
            for slope, icon in (
                (Slope.FLAT, ft.Icons.TRENDING_FLAT),
                (Slope.HILLY, ft.Icons.TRENDING_UP),
            )
        ]
