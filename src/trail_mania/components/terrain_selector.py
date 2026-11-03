"""Terrain selection using bundled SVG and built-in Flet icons."""

from pathlib import Path
from typing import Self

import flet as ft

from trail_mania.components.choice_selector import ChoiceSelector, selector_segment
from trail_mania.session_types import Terrain


def _tabler_icon(name: str, label: str) -> ft.Image:
    """Load a bundled Tabler SVG as a tinted selector image.

    Parameters
    ----------
    name : str
        Basename of an SVG in the adjacent icons directory, without extension.
    label : str
        French tooltip and accessibility label.

    Returns
    -------
    ft.Image
        Black-tinted SVG image with fixed selector-icon dimensions.

    Raises
    ------
    OSError
        If the bundled icon cannot be read.

    Notes
    -----
    SVG bytes are embedded in the control so the client does not need a
    filesystem path or external asset URL. Licensing is recorded in icons/LICENSE.
    """
    return ft.Image(
        src=Path(__file__).with_name("icons").joinpath(f"{name}.svg").read_bytes(),
        width=27,
        height=27,
        color=ft.Colors.BLACK,
        tooltip=label,
        semantics_label=label,
    )


@ft.control
class TerrainSelector(ChoiceSelector):
    """Select an outdoor terrain or a treadmill.

    Notes
    -----
    Inherits the initially empty, single-choice behavior and on_change
    callback from ChoiceSelector. Selected values are stable keys:
    road, rolling, technical and treadmill.
    """

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build the selector's options in display order.

        Returns
        -------
        list of ft.Segment
            Fresh, labeled segments using the shared session-choice keys.
        """
        return [
            selector_segment(terrain, terrain.label, icon)
            for terrain, icon in (
                (Terrain.ROAD, _tabler_icon("road", Terrain.ROAD.label)),
                (Terrain.ROLLING, ft.Icons.ROUTE),
                (Terrain.TECHNICAL, ft.Icons.TERRAIN),
                (Terrain.TREADMILL, _tabler_icon("treadmill", Terrain.TREADMILL.label)),
            )
        ]
