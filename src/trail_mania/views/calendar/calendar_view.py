from calendar import MONDAY, Calendar
from collections.abc import Callable
from datetime import date, timedelta
from typing import Final, Self

import flet as ft

from trail_mania.views.calendar._calendar_cells import (
    CELL_SPACING,
    WEEKDAY_NAMES,
    build_month_cell,
    build_week_cell,
    build_weekday_text,
)
from trail_mania.views.calendar._calendar_pager import CalendarPager


_MONTH_NAMES: Final[tuple[str, ...]] = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)
_MONTH_WEEK_SLOTS: Final[int] = 6

# (calendar year, month) or (ISO year, week), depending on the view.
type Period = tuple[int, int]


@ft.control
class CalendarView(ft.Container):
    """Display monthly and weekly calendars with independent selected periods.

    Attributes
    ----------
    selected_month : tuple of (int, int)
        Calendar year and month displayed by the monthly view.
    selected_week : tuple of (int, int)
        ISO year and week number displayed by the weekly view.

    Notes
    -----
    Both periods initially contain today's date. Switching views preserves
    their selected periods. Headers stay fixed while calendar grids slide.
    """

    def init(self: Self) -> None:
        """Initialize the selected periods and build the default monthly view.

        Notes
        -----
        Flet calls this hook during control construction. Initial periods use
        the current local date.
        """
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER

        today = date.today()
        self.selected_month: Period = (today.year, today.month)
        week_year, week, _ = today.isocalendar()
        self.selected_week: Period = (week_year, week)
        self._pager: CalendarPager | None = None

        self._period_content: ft.Container = ft.Container(
            expand=True,
            alignment=ft.Alignment.TOP_CENTER,
            content=self._build_month_view(),
        )
        self.content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self._build_selector(), self._period_content],
        )

    def _build_selector(self: Self) -> ft.Row:
        """Build the centered month/week selector.

        Returns
        -------
        ft.Row
            A row containing a segmented button with exactly one selected view.
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
                    on_change=self._on_view_change,
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

    def _build_month_view(self: Self) -> ft.Column:
        """Build the header and pager for the selected month.

        Returns
        -------
        ft.Column
            The monthly view with a French title and three prepared grids.
        """
        year, month = self.selected_month
        return self._build_period_view(
            title=f"{_MONTH_NAMES[month - 1]} {year}",
            reference_title="Septembre 8888",
            previous_tooltip="Mois précédent",
            next_tooltip="Mois suivant",
            build_calendar=self._build_month_calendar,
            period_at_offset=self._month_at_offset,
            on_change=self._change_month,
        )

    def _build_week_view(self: Self) -> ft.Column:
        """Build the header and pager for the selected ISO week.

        Returns
        -------
        ft.Column
            The weekly view with its ISO week title and three prepared grids.
        """
        year, week = self.selected_week
        return self._build_period_view(
            title=f"Semaine {week} - {year}",
            reference_title="Semaine 88 - 8888",
            previous_tooltip="Semaine précédente",
            next_tooltip="Semaine suivante",
            build_calendar=self._build_week_calendar,
            period_at_offset=self._week_at_offset,
            on_change=self._change_week,
        )

    def _build_period_view(
        self: Self,
        *,
        title: str,
        reference_title: str,
        previous_tooltip: str,
        next_tooltip: str,
        build_calendar: Callable[[Period], ft.Control],
        period_at_offset: Callable[[int], Period],
        on_change: Callable[[int], None],
    ) -> ft.Column:
        """Compose a period header and replace the active calendar pager.

        Parameters
        ----------
        title : str
            Title of the selected period.
        reference_title : str
            Invisible text reserving a stable width for the title.
        previous_tooltip : str
            Tooltip for the previous-period arrow.
        next_tooltip : str
            Tooltip for the next-period arrow.
        build_calendar : callable
            Build a grid from a year/month or ISO year/week tuple.
        period_at_offset : callable
            Resolve a signed period offset relative to the selected period.
        on_change : callable
            Navigate by a signed period offset and rebuild the active view.

        Returns
        -------
        ft.Column
            The fixed header followed by the swipeable calendar viewport.
        """
        header = self._build_period_header(
            title=title,
            reference_title=reference_title,
            previous_tooltip=previous_tooltip,
            next_tooltip=next_tooltip,
            on_change=on_change,
        )
        viewport_width = 0.0
        if self._pager is not None:
            # Reuse the measured width until the replacement receives a size event.
            viewport_width = self._pager.viewport_width
            self._pager.deactivate()
        self._pager = CalendarPager(
            calendars=(
                build_calendar(period_at_offset(-1)),
                build_calendar(period_at_offset(0)),
                build_calendar(period_at_offset(1)),
            ),
            spacing=CELL_SPACING,
            viewport_width=viewport_width,
            on_change=on_change,
            on_update=self.update,
        )
        return ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[header, self._pager.control],
        )

    def _build_period_header(
        self: Self,
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

    def _build_month_calendar(self: Self, period: Period) -> ft.Column:
        """Build a Monday-first monthly grid with six equal-height week slots.

        Parameters
        ----------
        period : tuple of (int, int)
            Calendar year and month to display.

        Returns
        -------
        ft.Column
            Weekday headings and complete weeks, including adjacent-month days.
            Unused week slots remain transparent below the grid.
        """
        weeks = Calendar(firstweekday=MONDAY).monthdatescalendar(*period)
        today = date.today()
        rows: list[ft.Control] = [
            ft.Row(
                expand=True,
                spacing=CELL_SPACING,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[build_month_cell(day, today, period) for day in week],
            )
            for week in weeks
        ]
        # Six equal slots keep cell heights stable across months.
        # Missing weeks leave transparent space below the grid.
        rows.extend(ft.Container(expand=True) for _ in range(_MONTH_WEEK_SLOTS - len(weeks)))
        return ft.Column(
            expand=True,
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self._build_weekday_header(),
                ft.Column(
                    expand=True,
                    spacing=CELL_SPACING,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=rows,
                ),
            ],
        )

    def _build_weekday_header(self: Self) -> ft.Row:
        """Build equally spaced weekday headings from Monday to Sunday.

        Returns
        -------
        ft.Row
            Seven centered French weekday abbreviations.
        """
        return ft.Row(
            spacing=CELL_SPACING,
            controls=[
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=build_weekday_text(weekday),
                )
                for weekday in WEEKDAY_NAMES
            ],
        )

    def _build_week_calendar(self: Self, period: Period) -> ft.Column:
        """Build seven stacked day cells for an ISO week.

        Parameters
        ----------
        period : tuple of (int, int)
            ISO year and week number to display.

        Returns
        -------
        ft.Column
            Equally expanding day cells ordered from Monday to Sunday.
        """
        monday = date.fromisocalendar(*period, 1)
        today = date.today()
        return ft.Column(
            expand=True,
            spacing=CELL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                build_week_cell(monday + timedelta(days=offset), today, weekday)
                for offset, weekday in enumerate(WEEKDAY_NAMES)
            ],
        )

    def _month_at_offset(self: Self, offset: int) -> Period:
        """Resolve a month relative to the selected month.

        Parameters
        ----------
        offset : int
            Signed number of months to move; zero keeps the selected month.

        Returns
        -------
        tuple of (int, int)
            Calendar year and month after applying the offset.
        """
        year, month = self.selected_month
        year_offset, month_index = divmod(month - 1 + offset, 12)
        return year + year_offset, month_index + 1

    def _week_at_offset(self: Self, offset: int) -> Period:
        """Resolve an ISO week relative to the selected week.

        Parameters
        ----------
        offset : int
            Signed number of weeks to move; zero keeps the selected week.

        Returns
        -------
        tuple of (int, int)
            ISO year and week number after applying the offset.
        """
        monday = date.fromisocalendar(*self.selected_week, 1)
        selected_date = monday + timedelta(weeks=offset)
        week_year, week, _ = selected_date.isocalendar()
        return week_year, week

    def _change_month(self: Self, offset: int) -> None:
        """Shift the selected month and rebuild the monthly view.

        Parameters
        ----------
        offset : int
            Signed number of months to move relative to the selected month.
        """
        self.selected_month = self._month_at_offset(offset)
        self._period_content.content = self._build_month_view()
        self.update()

    def _change_week(self: Self, offset: int) -> None:
        """Shift the selected ISO week and rebuild the weekly view.

        Parameters
        ----------
        offset : int
            Signed number of weeks to move relative to the selected ISO week.
        """
        self.selected_week = self._week_at_offset(offset)
        self._period_content.content = self._build_week_view()
        self.update()

    def _on_view_change(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Display the view selected by the month/week selector.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event whose control identifies the requested view.
        """
        self._period_content.content = (
            self._build_month_view()
            if event.control.selected == ["month"]
            else self._build_week_view()
        )
        self.update()
