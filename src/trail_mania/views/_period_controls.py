"""Period controls shared by the calendar and statistics views."""

from collections.abc import Callable
from typing import Final

import flet as ft

MONTH_NAMES: Final[tuple[str, ...]] = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)


def build_period_selector(on_change: Callable[[ft.Event[ft.SegmentedButton]], None]) -> ft.Row:
    """Build the centered month/week selector.

    Parameters
    ----------
    on_change : callable
        Callback receiving a segmented-button event when the mode changes.

    Returns
    -------
    ft.Row
        Row containing a segmented button with exactly one selected mode.

    Notes
    -----
    The initial selection is month. Values exchanged with the callback are
    month and week; their visible labels remain French. The owning view
    preserves its period selections and handles loading and client updates.
    """
    return ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.SegmentedButton(
                selected=["month"],
                allow_empty_selection=False,
                allow_multiple_selection=False,
                show_selected_icon=False,
                on_change=on_change,
                style=ft.ButtonStyle(
                    shape=ft.StadiumBorder(),
                    bgcolor={
                        ft.ControlState.SELECTED: ft.Colors.PRIMARY_CONTAINER,
                        ft.ControlState.DEFAULT: ft.Colors.SURFACE,
                    },
                    color={
                        ft.ControlState.SELECTED: ft.Colors.ON_PRIMARY_CONTAINER,
                        ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE,
                    },
                ),
                segments=[
                    ft.Segment(value="month", label="Mois"),
                    ft.Segment(value="week", label="Semaine"),
                ],
            ),
        ],
    )


def build_period_header(
    title: str,
    reference_title: str,
    previous_tooltip: str,
    next_tooltip: str,
    on_change: Callable[[int], None],
) -> ft.Row:
    """Build a period title between two fixed-position navigation arrows.

    Parameters
    ----------
    title : str
        Visible title of the selected period.
    reference_title : str
        Invisible text defining the width of the title area.
    previous_tooltip : str
        Tooltip for the left arrow.
    next_tooltip : str
        Tooltip for the right arrow.
    on_change : callable
        Receive -1 for the previous period or 1 for the next period.

    Returns
    -------
    ft.Row
        A centered title and arrows that apply navigation immediately.
    """
    title_style = ft.TextStyle(
        size=24,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.BLACK,
    )
    return ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                icon_color=ft.Colors.BLACK,
                tooltip=previous_tooltip,
                on_click=lambda event: on_change(-1),
            ),
            ft.Stack(
                alignment=ft.Alignment.CENTER,
                controls=[
                    # Reserve a fixed title width so the arrows do not move.
                    ft.Text(
                        reference_title,
                        style=title_style,
                        no_wrap=True,
                        opacity=0,
                    ),
                    ft.Text(title, style=title_style, no_wrap=True),
                ],
            ),
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                icon_color=ft.Colors.BLACK,
                tooltip=next_tooltip,
                on_click=lambda event: on_change(1),
            ),
        ],
    )

