"""Heart-rate zone chart and legend shared by running session details."""

from math import cos, pi, sin
from typing import Final

import flet as ft
import flet.canvas as cv

from trail_mania.session_colors import SESSION_COLORS
from trail_mania.session_types import SessionType

# Reuse the session palette in increasing zone-intensity order, Z1 through Z5.
_ZONE_TYPES: Final[tuple[SessionType, ...]] = (
    SessionType.LONG_RUN, SessionType.EASY_RUN, SessionType.STEADY_RUN,
    SessionType.THRESHOLD, SessionType.VO2MAX,
)
_SIZE: Final[int] = 192
_CENTER: Final[float] = _SIZE / 2
# Leave room for the stroked outline inside the canvas bounds.
_RADIUS: Final[float] = _CENTER - 0.8


def zone_chart(percentages: tuple[float | None, ...]) -> ft.Row:
    """Draw heart-rate zone shares and their five-entry legend.

    Parameters
    ----------
    percentages : tuple of float or None
        Five shares in Z1-to-Z5 order. Populated shares are nonnegative and
        sum to 100; all entries are None when no zone duration was recorded.

    Returns
    -------
    ft.Row
        Wrapping row containing the accessible pie chart and legend. When
        all shares are absent or zero, a French message replaces the chart.

    Raises
    ------
    ValueError
        If the tuple does not contain exactly five entries.

    Notes
    -----
    Sector angles use unrounded shares; only legend captions round to one
    decimal place. Zero-share zones keep their labels without creating a
    sector. Colors follow the session palette in increasing intensity order.
    """
    shapes: list[cv.Shape] = []
    boundaries: list[float] = []
    border = ft.Paint(color=ft.Colors.BLACK, style=ft.PaintingStyle.STROKE, stroke_width=1.2)
    legend: list[ft.Control] = []
    start = -pi / 2
    for index, (percentage, session_type) in enumerate(zip(percentages, _ZONE_TYPES, strict=True), 1):
        color = SESSION_COLORS[session_type]
        caption = f"Z{index} : {percentage:.1f} %".replace(".", ",") if percentage is not None else f"Z{index} : —"
        legend.append(ft.Row(tight=True, controls=[
            ft.Container(width=16, height=16, bgcolor=color),
            ft.Text(caption, color=ft.Colors.BLACK),
        ]))
        if percentage:
            boundaries.append(start)
            sweep = percentage / 100 * 2 * pi
            shapes.append(cv.Arc(
                _CENTER - _RADIUS, _CENTER - _RADIUS, 2 * _RADIUS, 2 * _RADIUS,
                start_angle=start, sweep_angle=sweep, use_center=True,
                paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL),
            ))
            start += sweep
    if len(boundaries) > 1:
        # A single full-circle sector needs no radial separator.
        shapes.extend(cv.Line(
            _CENTER, _CENTER,
            _CENTER + _RADIUS * cos(angle), _CENTER + _RADIUS * sin(angle), paint=border,
        ) for angle in boundaries)
    if shapes:
        shapes.append(cv.Circle(_CENTER, _CENTER, _RADIUS, paint=border))
    chart = (
        ft.Semantics(label="Répartition des zones de fréquence cardiaque",
                     content=cv.Canvas(shapes=shapes, width=_SIZE, height=_SIZE))
        if shapes else ft.Text("Aucune durée de zone renseignée.", color=ft.Colors.BLACK)
    )
    return ft.Row(wrap=True, spacing=24, run_spacing=16,
                  controls=[chart, ft.Column(controls=legend)])
