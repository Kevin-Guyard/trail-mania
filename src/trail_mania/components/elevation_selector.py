"""Single-choice selection of flat or hilly session profiles."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import (
    ChoiceSelector,
    selector_icon,
    selector_segment,
)
from trail_mania.session_types import Slope


def slope_icon(slope: Slope) -> ft.Icon:
    """Build the slope pictogram shared by selectors and table cells.

    Parameters
    ----------
    slope : Slope
        Flat or hilly profile to represent.

    Returns
    -------
    ft.Icon
        Fresh black trend icon with the canonical French tooltip and
        accessibility label.
    """
    icon = ft.Icons.TRENDING_FLAT if slope == Slope.FLAT else ft.Icons.TRENDING_UP
    return selector_icon(icon, slope.label)


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
            selector_segment(slope, slope.label, slope_icon(slope))
            for slope in Slope
        ]
