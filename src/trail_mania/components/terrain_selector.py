"""Terrain selection using bundled SVG and built-in Flet icons."""

from functools import cache
from pathlib import Path
from typing import Self

import flet as ft

from trail_mania.components.choice_selector import (
    ChoiceSelector,
    selector_icon,
    selector_segment,
)
from trail_mania.session_types import Terrain


# Cache asset bytes, not Flet controls: each rendered icon needs its own parent.
@cache
def _tabler_svg(name: str) -> bytes:
    """Read and cache the bytes of a bundled Tabler SVG asset.

    Parameters
    ----------
    name : str
        Basename in the adjacent icons directory, without the SVG extension.

    Returns
    -------
    bytes
        SVG source reused by every rendered instance of this asset.

    Raises
    ------
    OSError
        If the asset is missing or cannot be read on its first request.

    Notes
    -----
    The cache lasts for the Python process. Each caller still creates its
    own image control so rows do not share control instances.
    """
    return Path(__file__).with_name("icons").joinpath(f"{name}.svg").read_bytes()


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
        src=_tabler_svg(name),
        width=27,
        height=27,
        color=ft.Colors.BLACK,
        tooltip=label,
        semantics_label=label,
    )


def terrain_icon(terrain: Terrain) -> ft.Control:
    """Build the terrain pictogram shared by selectors and table cells.

    Parameters
    ----------
    terrain : Terrain
        Supported terrain whose canonical label identifies the pictogram.

    Returns
    -------
    ft.Control
        Fresh black SVG image for road or treadmill, or a built-in icon for
        rolling or technical terrain, with a tooltip and accessibility label.

    Raises
    ------
    OSError
        If a requested bundled SVG has not been cached and cannot be read.
    """
    if terrain == Terrain.ROAD:
        return _tabler_icon("road", terrain.label)
    if terrain == Terrain.TREADMILL:
        return _tabler_icon("treadmill", terrain.label)
    icon = ft.Icons.ROUTE if terrain == Terrain.ROLLING else ft.Icons.TERRAIN
    return selector_icon(icon, terrain.label)


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
            selector_segment(terrain, terrain.label, terrain_icon(terrain))
            for terrain in Terrain
        ]
