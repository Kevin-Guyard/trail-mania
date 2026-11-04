"""Coordinate period navigation, data loading and the statistics table."""

from calendar import monthrange
from datetime import date, timedelta
from typing import Literal, Self

import flet as ft

from trail_mania.session_repository import get_running_sessions_between
from trail_mania.session_statistics import summarize_sessions
from trail_mania.views._period_controls import (
    MONTH_NAMES,
    build_period_header,
    build_period_selector,
)
from trail_mania.views.statistics._table import StatisticsTable


@ft.control
class StatisticsView(ft.Container):
    """Display running totals with independent month and ISO-week selections.

    Attributes
    ----------
    selected_month : tuple of (int, int)
        Calendar year and month selected for monthly statistics.
    selected_week : tuple of (int, int)
        ISO week year and week number selected for weekly statistics.

    Notes
    -----
    Both selections initially contain today. Navigation and tab activation
    reload storage; the table and its scroll containers remain in place.
    The selector and header share their appearance with the calendar view.
    Storage must be initialized before constructing the control.
    """

    def init(self: Self) -> None:
        """Initialize the period selections, persistent controls and monthly totals.

        Notes
        -----
        Flet calls this hook during construction. Initial selections use the
        local date, with the ISO year used for the weekly selection. Loading
        initial totals does not send a client update.
        """
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER
        today = date.today()
        self.selected_month: tuple[int, int] = (today.year, today.month)
        # Around New Year, the ISO week year can differ from the calendar year.
        year, week, _ = today.isocalendar()
        self.selected_week: tuple[int, int] = (year, week)
        self._mode: Literal["month", "week"] = "month"
        # Keep the table and its scroll containers mounted across refreshes.
        self._header: ft.Container = ft.Container()
        self._table: StatisticsTable = StatisticsTable()
        self.content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                build_period_selector(self._on_view_change),
                ft.Column(
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        self._header,
                        ft.Column(
                            expand=True,
                            scroll=ft.ScrollMode.AUTO,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            controls=[ft.Row(
                                alignment=ft.MainAxisAlignment.CENTER,
                                scroll=ft.ScrollMode.AUTO,
                                controls=[self._table],
                            )],
                        ),
                    ],
                ),
            ],
        )
        self.refresh()

    def _on_view_change(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Activate the selected statistics mode and update the displayed totals.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Event from the shared selector, containing exactly one selected
            mode: month or week.

        Notes
        -----
        Switching modes preserves both period selections. The destination
        period is reloaded before the control sends its client update.
        """
        self._mode = "month" if event.control.selected == ["month"] else "week"
        self.refresh()
        self.update()

    def _change_period(self: Self, offset: int) -> None:
        """Move the active period, reload its statistics and update the view.

        Parameters
        ----------
        offset : int
            Signed number of months or ISO weeks to move, depending on the
            active mode. Zero reloads the current period.

        Notes
        -----
        Month arithmetic crosses calendar years; week arithmetic starts from
        the selected Monday and resolves the destination's ISO year and week.
        The inactive mode's selection remains unchanged.
        """
        if self._mode == "month":
            year, month = self.selected_month
            year_offset, month_index = divmod(month - 1 + offset, 12)
            self.selected_month = (year + year_offset, month_index + 1)
        else:
            monday = date.fromisocalendar(*self.selected_week, 1) + timedelta(weeks=offset)
            year, week, _ = monday.isocalendar()
            self.selected_week = (year, week)
        self.refresh()
        self.update()

    def refresh(self: Self) -> None:
        """Reload totals and the period header without sending a client update.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If reading or converting stored measurements fails.
        OSError
            If the database storage directory cannot be accessed or created.

        Notes
        -----
        Monthly ranges include only the selected month's dates. Weekly
        ranges include Monday through Sunday, including dates from adjacent
        calendar years. Period selections and the existing table are retained.
        The caller sends the final control or page update after refreshing.
        """
        if self._mode == "month":
            year, month = self.selected_month
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            title = f"{MONTH_NAMES[month - 1]} {year}"
            reference_title = "Septembre 8888"
            previous_tooltip, next_tooltip = "Mois précédent", "Mois suivant"
        else:
            year, week = self.selected_week
            start = date.fromisocalendar(year, week, 1)
            end = start + timedelta(days=6)
            title = f"Semaine {week} - {year}"
            reference_title = "Semaine 88 - 8888"
            previous_tooltip, next_tooltip = "Semaine précédente", "Semaine suivante"

        statistics = summarize_sessions(get_running_sessions_between(start, end))
        self._table.set_statistics(statistics)
        self._header.content = build_period_header(
            title, reference_title, previous_tooltip, next_tooltip, self._change_period,
        )
