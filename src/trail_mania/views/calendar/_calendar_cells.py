from datetime import date
from typing import Final, cast

import flet as ft


CELL_SPACING: Final[int] = 4
WEEKDAY_NAMES: Final[tuple[str, ...]] = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")

_DATE_FONT_SIZE: Final[int] = 14
_DATE_LABEL_HEIGHT: Final[int] = 24
_WEEK_DATE_WIDTH: Final[int] = 48


def build_weekday_text(weekday: str) -> ft.Text:
    """Build the weekday text shared by both calendar layouts.

    Parameters
    ----------
    weekday : str
        Weekday abbreviation to display.

    Returns
    -------
    ft.Text
        Black weekday text using the common size and weight.
    """
    return ft.Text(
        weekday,
        size=12,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.BLACK,
    )


def build_month_cell(day: date, today: date, month: tuple[int, int]) -> ft.Container:
    """Build a monthly day cell with a number in its upper-right corner.

    Parameters
    ----------
    day : datetime.date
        Date represented by the cell.
    today : datetime.date
        Current date used to determine whether to show the today badge.
    month : tuple of (int, int)
        Calendar year and month represented by the grid.

    Returns
    -------
    ft.Container
        A bordered day cell with muted adjacent-month dates. Today's circular
        badge appears only when the date belongs to the represented month.
    """
    in_month = (day.year, day.month) == month
    is_today = day == today and in_month
    label = ft.Container(
        top=4,
        right=4,
        width=_DATE_LABEL_HEIGHT,
        height=_DATE_LABEL_HEIGHT,
        shape=ft.BoxShape.CIRCLE,
        bgcolor=ft.Colors.BLACK if is_today else None,
        alignment=ft.Alignment.CENTER,
        # Two pixels of bottom padding shift the text center one pixel upward.
        padding=ft.Padding.only(bottom=2) if is_today else 0,
        content=_build_date_text(str(day.day), is_today=is_today, muted=not in_month),
    )
    return _build_day_cell(day, label)


def build_week_cell(day: date, today: date, weekday: str) -> ft.Container:
    """Build a weekly day cell with its weekday and day/month date.

    Parameters
    ----------
    day : datetime.date
        Date represented by the cell.
    today : datetime.date
        Current date used to determine whether to show the today badge.
    weekday : str
        Weekday abbreviation displayed in the upper-left corner.

    Returns
    -------
    ft.Container
        A bordered day cell with the date in the upper-right corner and an
        oval badge when it represents today.
    """
    is_today = day == today
    label = ft.Container(
        top=4,
        left=4,
        right=4,
        height=_DATE_LABEL_HEIGHT,
        alignment=ft.Alignment.TOP_RIGHT,
        content=ft.Container(
            width=_WEEK_DATE_WIDTH,
            height=_DATE_LABEL_HEIGHT,
            border_radius=ft.BorderRadius.all(12),
            bgcolor=ft.Colors.BLACK if is_today else None,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.only(bottom=2) if is_today else 0,
            content=_build_date_text(
                f"{day.day:02d}/{day.month:02d}", is_today=is_today
            ),
            on_size_change=_resize_week_date_label,
        ),
    )
    weekday_label = ft.Container(
        top=4,
        left=8,
        height=_DATE_LABEL_HEIGHT,
        alignment=ft.Alignment.CENTER_LEFT,
        content=build_weekday_text(weekday),
    )
    return _build_day_cell(day, label, weekday_label)


def _build_date_text(value: str, *, is_today: bool, muted: bool = False) -> ft.Text:
    """Build centered date text with the shared calendar typography.

    Parameters
    ----------
    value : str
        Formatted day number or day/month date.
    is_today : bool
        Whether to use bold white text for today's badge.
    muted : bool, optional
        Whether to use gray text for an adjacent-month date. Defaults to False.

    Returns
    -------
    ft.Text
        A single-line label whose today styling takes precedence over muting.
    """
    color = ft.Colors.GREY_400 if muted else ft.Colors.BLACK
    return ft.Text(
        value,
        size=_DATE_FONT_SIZE,
        text_align=ft.TextAlign.CENTER,
        no_wrap=True,
        style=ft.TextStyle(height=1, letter_spacing=0),
        color=ft.Colors.WHITE if is_today else color,
        weight=ft.FontWeight.W_600 if is_today else ft.FontWeight.W_400,
    )


def _build_day_cell(
    day: date,
    date_label: ft.Container,
    weekday_label: ft.Container | None = None,
) -> ft.Container:
    """Compose the shared background, labels, border, and full-date tooltip.

    Parameters
    ----------
    day : datetime.date
        Date used for the tooltip in day/month/year format.
    date_label : ft.Container
        Positioned date label or badge.
    weekday_label : ft.Container or None, optional
        Positioned weekday label for the weekly layout. Defaults to None.

    Returns
    -------
    ft.Container
        An expanding rounded cell with a white background below the labels
        and a black foreground border.
    """
    # Separate the background from labels to allow future split background fills.
    layers: list[ft.Control] = [
        ft.Container(
            bgcolor=ft.Colors.WHITE,
            border_radius=ft.BorderRadius.all(11),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ),
        date_label,
    ]
    if weekday_label is not None:
        layers.append(weekday_label)

    return ft.Container(
        expand=True,
        padding=1,
        # Draw the border above the background, including at rounded corners.
        foreground_decoration=ft.BoxDecoration(
            border=ft.Border.all(1, ft.Colors.BLACK),
            border_radius=ft.BorderRadius.all(12),
        ),
        tooltip=f"{day.day:02d}/{day.month:02d}/{day.year}",
        content=ft.Stack(fit=ft.StackFit.EXPAND, controls=layers),
    )


def _resize_week_date_label(event: ft.LayoutSizeChangeEvent[ft.Container]) -> None:
    """Fit weekly date text to its label width without exceeding its base size.

    Parameters
    ----------
    event : ft.LayoutSizeChangeEvent[ft.Container]
        Size event from the date badge container, whose content is an ft.Text.

    Notes
    -----
    Nonpositive widths are ignored. Resizing changes only the font size,
    preserving the badge dimensions and optical alignment.
    """
    if event.width <= 0:
        return
    text = cast(ft.Text, event.control.content)
    size = min(_DATE_FONT_SIZE, _DATE_FONT_SIZE * event.width / _WEEK_DATE_WIDTH)
    if text.size != size:
        text.size = size
        event.control.update()
