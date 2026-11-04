"""Build calendar day cells and bind individual session bands to navigation."""

from datetime import date
from collections.abc import Callable, Sequence
from typing import Final, cast

import flet as ft

from trail_mania.session_colors import SESSION_COLORS
from trail_mania.session_types import SessionType

CELL_SPACING: Final[int] = 4
WEEKDAY_NAMES: Final[tuple[str, ...]] = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")

_DATE_FONT_SIZE: Final[int] = 14
_DATE_LABEL_HEIGHT: Final[int] = 24
_WEEK_DATE_WIDTH: Final[int] = 48
_WEEK_SESSION_GUTTER: Final[int] = _WEEK_DATE_WIDTH + 12


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


def build_month_cell(
    day: date, today: date, month: tuple[int, int],
    session_types: Sequence[SessionType] = (),
    session_actions: Sequence[Callable[[], None] | None] = (),
) -> ft.Container:
    """Build a monthly day cell with a number in its upper-right corner.

    Parameters
    ----------
    day : datetime.date
        Date represented by the cell.
    today : datetime.date
        Current date used to determine whether to show the today badge.
    month : tuple of (int, int)
        Calendar year and month represented by the grid.
    session_types : sequence of SessionType, optional
        Families in band order, retaining duplicates; defaults to no sessions.
    session_actions : sequence of callable or None, optional
        Matching zero-argument detail actions. Missing entries and None leave
        their bands without an action; defaults to an empty sequence.

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
    return _build_day_cell(day, label, session_types=session_types,
                           session_actions=session_actions, muted=not in_month)


def build_week_cell(
    day: date, today: date, weekday: str,
    session_types: Sequence[SessionType] = (),
    session_labels: Sequence[str] = (),
    session_actions: Sequence[Callable[[], None] | None] = (),
) -> ft.Container:
    """Build a weekly day cell with its weekday and day/month date.

    Parameters
    ----------
    day : datetime.date
        Date represented by the cell.
    today : datetime.date
        Current date used to determine whether to show the today badge.
    weekday : str
        Weekday abbreviation displayed in the upper-left corner.
    session_types : sequence of SessionType, optional
        Families in band order, retaining duplicates; defaults to no sessions.
    session_labels : sequence of str, optional
        Descriptions in band order. Missing or empty entries omit the text;
        strength bands never display descriptions. Defaults to no labels.
    session_actions : sequence of callable or None, optional
        Matching zero-argument detail actions. Missing entries and None leave
        their bands without an action; defaults to an empty sequence.

    Returns
    -------
    ft.Container
        A bordered day cell with the date in the upper-right corner and an
        oval badge when it represents today. Session details are centered in
        their colored bands, between reserved weekday and date margins.
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
    return _build_day_cell(
        day, label, weekday_label, session_types=session_types, session_labels=session_labels,
        session_actions=session_actions,
    )


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
    *,
    session_types: Sequence[SessionType] = (),
    session_labels: Sequence[str] = (),
    session_actions: Sequence[Callable[[], None] | None] = (),
    muted: bool = False,
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
    session_types : sequence of SessionType, optional
        Families supplying band colors in display order; defaults to empty.
    session_labels : sequence of str, optional
        Optional descriptions in band order, used only for the weekly layout.
        Missing descriptions leave their bands empty; defaults to empty.
    session_actions : sequence of callable or None, optional
        Zero-argument callbacks in band order. None and missing entries leave
        the corresponding band without a click handler; defaults to empty.
    muted : bool, optional
        Whether to use a gray border for an adjacent-month date. Defaults to False.

    Returns
    -------
    ft.Container
        An expanding rounded cell with session colors below the labels
        and a black or muted gray foreground border. Empty days remain white.
    """
    # Labels are decorative overlays: taps must reach the session band below.
    date_label.ignore_interactions = True
    if weekday_label is not None:
        weekday_label.ignore_interactions = True
    bands: list[ft.Control] = []
    def click_handler(index: int) -> Callable[[ft.Event[ft.Container]], None] | None:
        """Adapt a band's optional detail action to a Flet click callback.

        Parameters
        ----------
        index : int
            Nonnegative index in the parallel session-band sequences.

        Returns
        -------
        callable or None
            Event callback bound to this action, or None when no matching
            action exists. The Flet event payload is unused.
        """
        action = session_actions[index] if index < len(session_actions) else None
        return (lambda event: action()) if action is not None else None

    def session_label(index: int) -> ft.Container | None:
        """Build a nonempty running description for a weekly band.

        Parameters
        ----------
        index : int
            Valid zero-based index in ``session_types``.

        Returns
        -------
        ft.Container or None
            Centered description, or None for monthly cells, strength sessions
            and absent or empty description entries.
        """
        if weekday_label is None or session_types[index] == SessionType.LEG_STRENGTH:
            return None
        if index >= len(session_labels) or not session_labels[index]:
            return None
        return _build_week_session_label(session_labels[index])

    for index, session_type in enumerate(session_types):
        if bands:
            bands.append(ft.Container(height=1, bgcolor=ft.Colors.BLACK_26))
        bands.append(ft.Container(
            expand=True,
            bgcolor=SESSION_COLORS[session_type],
            content=session_label(index),
            on_click=click_handler(index),
        ))
    layers: list[ft.Control] = [
        ft.Container(
            bgcolor=SESSION_COLORS[session_types[0]] if session_types else ft.Colors.WHITE,
            border_radius=ft.BorderRadius.all(11),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            on_click=click_handler(0) if len(session_types) == 1 else None,
            content=ft.Column(
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=bands,
            ) if len(session_types) > 1 else (
                session_label(0) if session_types else None
            ),
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
            border=ft.Border.all(1, ft.Colors.GREY_400 if muted else ft.Colors.BLACK),
            border_radius=ft.BorderRadius.all(12),
        ),
        tooltip=f"{day.day:02d}/{day.month:02d}/{day.year}",
        content=ft.Stack(fit=ft.StackFit.EXPAND, controls=layers),
    )


def _build_week_session_label(description: str) -> ft.Container:
    """Center session details within a band and keep the day/date gutters clear.

    Parameters
    ----------
    description : str
        Running-session description to display within the weekly band.

    Returns
    -------
    ft.Container
        Centered, clipped single-line description with equal side gutters.

    Notes
    -----
    Equal side margins preserve the cell's horizontal center. A single line
    with ellipsis handles narrow cells; clipping keeps text inside short bands.
    """
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.symmetric(horizontal=_WEEK_SESSION_GUTTER),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Text(
            description,
            size=13,
            weight=ft.FontWeight.W_400,
            color=ft.Colors.BLACK,
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
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
