"""Integration coverage for statistics rendering, periods and tab refreshes."""

import os
import tempfile
import unittest
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Self, cast
from unittest.mock import Mock, patch

import flet as ft

from trail_mania.app import change_page
from trail_mania.database import initialize_database
from trail_mania.session_repository import create_session
from trail_mania.session_types import (
    SessionDetailValue,
    SessionDetailValues,
    SessionType,
)
from trail_mania.views.statistics import StatisticsView, statistics_view


class FixedDate(date):
    """Provide a stable local date near an ISO week-year boundary.

    Notes
    -----
    The view's date class is patched with this subclass so initialization
    selects January 2027 and ISO week 53 of 2026 deterministically.
    """

    @classmethod
    def today(cls: type[Self]) -> Self:
        """Return the fixed date used to initialize statistics selections.

        Returns
        -------
        Self
            January 1, 2027, constructed with the receiving date subclass.
        """
        return cls(2027, 1, 1)


def walk(control: ft.Control) -> Iterator[ft.Control]:
    """Traverse a control's content and controls branches in depth-first order.

    Parameters
    ----------
    control : ft.Control
        Root control whose descendants should be inspected.

    Yields
    ------
    ft.Control
        The root followed by descendants exposed through content or controls.
        Other properties, such as table cells, are inspected separately.
    """
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", []):
        yield from walk(child)


class StatisticsViewTests(unittest.TestCase):
    """Verify rendered statistics against records stored in an isolated database.

    Notes
    -----
    Tests use a fixed local date and mock client updates, while retaining the
    real repository and aggregation path except when checking query bounds.
    """

    def setUp(self: Self) -> None:
        """Initialize isolated storage, a fixed date and mocked Flet updates.

        Notes
        -----
        Registered context managers restore patches and remove the temporary
        database after each test, including when an assertion fails.
        """
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        self.enterContext(patch.object(statistics_view, "date", FixedDate))
        self.enterContext(patch.object(ft.Control, "update", autospec=True))
        initialize_database()

    @staticmethod
    def save(
        day: date,
        session_type: SessionType = SessionType.EASY_RUN,
        distance: str = "10.0",
        **measurements: SessionDetailValue,
    ) -> int:
        """Persist an endurance session with optional measurement overrides.

        Parameters
        ----------
        day : datetime.date
            Local calendar date assigned to the session.
        session_type : SessionType, optional
            Endurance family; defaults to easy endurance.
        distance : str, optional
            Decimal distance in kilometers; defaults to 10.0.
        **measurements : SessionDetailValue
            Overrides keyed by repository detail-column names, such as Z1,
            velocity or elevation_gain.

        Returns
        -------
        int
            Persistent identity of the created session.
        """
        values: SessionDetailValues = dict(
            field_type="Route", slope_type="Sans pente",
            distance=Decimal(distance), velocity=Decimal("10.0"),
            mean_HR=130, max_HR=150, RPE=Decimal("3.0"), comment="",
            **{f"Z{i}": timedelta(0) for i in range(1, 6)},
        )
        values.update(measurements)
        return create_session(day, session_type, values)

    @staticmethod
    def table(view: StatisticsView) -> ft.DataTable:
        """Locate the statistics table in a constructed view.

        Parameters
        ----------
        view : StatisticsView
            View whose rendered control tree should be inspected.

        Returns
        -------
        ft.DataTable
            Table containing the running-family and overall rows.
        """
        return next(control for control in walk(view) if isinstance(control, ft.DataTable))

    @classmethod
    def rows(cls: type[Self], view: StatisticsView) -> list[list[str]]:
        """Read all displayed table values in row and column order.

        Parameters
        ----------
        view : StatisticsView
            View containing the table under test.

        Returns
        -------
        list of list of str
            Cell captions, using the table schema's text-only cell contract.
        """
        return [[cast(ft.Text, cell.content).value for cell in row.cells] for row in cls.table(view).rows]

    @classmethod
    def distances(cls: type[Self], view: StatisticsView) -> list[list[str]]:
        """Read the family label and distance from each displayed row.

        Parameters
        ----------
        view : StatisticsView
            View containing the table under test.

        Returns
        -------
        list of list of str
            Two captions per row: its label and formatted distance.
        """
        return [[row[0], row[2]] for row in cls.rows(view)]

    @staticmethod
    def title(view: StatisticsView) -> str:
        """Read the visible period title while skipping the width-reserving text.

        Parameters
        ----------
        view : StatisticsView
            View whose period header should be inspected.

        Returns
        -------
        str
            French month/year or ISO week/year caption.
        """
        return next(control.value for control in walk(view)
                    if isinstance(control, ft.Text) and control.style is not None
                    and control.style.size == 24 and control.opacity != 0)

    @staticmethod
    def select(view: StatisticsView, mode: Literal["month", "week"]) -> None:
        """Select a statistics mode through the shared selector's callback.

        Parameters
        ----------
        view : StatisticsView
            View whose active mode should change.
        mode : {"month", "week"}
            Mode selected before dispatching the synthetic change event.

        Notes
        -----
        The view's selector always installs a callback accepting its change
        event, which narrows Flet's optional callback type for this helper.
        """
        selector = next(control for control in walk(view) if isinstance(control, ft.SegmentedButton))
        selector.selected = [mode]
        on_change = cast(Callable[[ft.Event[ft.SegmentedButton]], None], selector.on_change)
        on_change(ft.Event("change", selector))

    def test_month_sums_duplicates_and_includes_only_month_dates(self: Self) -> None:
        """Verify duplicate runs count while strength and adjacent months do not."""
        self.save(date(2026, 12, 31), distance="100.0")
        self.save(date(2027, 1, 1), distance="10.2")
        self.save(date(2027, 1, 1), distance="2.3")
        self.save(date(2027, 1, 31), SessionType.LONG_RUN, "20.0")
        self.save(date(2027, 2, 1), distance="200.0")
        create_session(date(2027, 1, 1), SessionType.LEG_STRENGTH)
        view = StatisticsView()
        self.assertEqual(self.title(view), "Janvier 2027")
        self.assertEqual(self.distances(view), [
            ["Sortie longue", "20,0 km"], ["Endurance fondamentale", "12,5 km"],
            ["Endurance active", "0,0 km"], ["Seuil", "0,0 km"],
            ["VO2max", "0,0 km"], ["Total", "32,5 km"],
        ])
        self.assertFalse(any(isinstance(control, ft.GestureDetector) for control in walk(view)))

    def test_iso_week_crosses_year_and_modes_preserve_periods(self: Self) -> None:
        """Verify inclusive ISO dates and independent month/week selections."""
        self.save(date(2026, 12, 27), distance="100.0")
        self.save(date(2026, 12, 28), distance="3.0")
        self.save(date(2027, 1, 3), distance="4.0")
        self.save(date(2027, 1, 4), distance="200.0")
        view = StatisticsView()
        self.select(view, "week")
        self.assertEqual(self.title(view), "Semaine 53 - 2026")
        self.assertEqual(self.distances(view)[-1], ["Total", "7,0 km"])
        view._change_period(1)
        self.assertEqual(self.title(view), "Semaine 1 - 2027")
        self.select(view, "month")
        view._change_period(-1)
        self.assertEqual(self.title(view), "Décembre 2026")
        self.select(view, "week")
        self.assertEqual(self.title(view), "Semaine 1 - 2027")

    def test_return_to_statistics_refreshes_new_sessions(self: Self) -> None:
        """Verify tab activation displays sessions added after view construction."""
        view = StatisticsView()
        self.save(date(2027, 1, 2), distance="4.2")
        page = Mock()
        container = ft.Container()
        change_page(ft.Event("change", ft.NavigationBar(selected_index=0)), page, [view], container)
        self.assertIs(container.content, view)
        self.assertEqual(self.distances(view)[-1], ["Total", "4,2 km"])
        page.update.assert_called_once()

    def test_persisted_intervals_contribute_to_rows_and_total(self: Self) -> None:
        """Verify threshold and VO2max distance and elevation reach all total rows."""
        common: SessionDetailValues = dict(
            field_type="Route", slope_type="Sans pente",
            duration_ON=Decimal(5), duration_OFF=Decimal(2),
            inclination=Decimal(10),
            RPE=Decimal("7.0"), comment="",
            **{f"Z{i}": timedelta(0) for i in range(1, 6)},
        )
        for session_type, repetitions in ((SessionType.THRESHOLD, 3), (SessionType.VO2MAX, 4)):
            values = dict(common)
            for i in range(1, repetitions + 1):
                values.update({f"velocity_ON_{i}": 12.0, f"mean_HR_ON_{i}": 150, f"max_HR_ON_{i}": 170})
                if i < repetitions:
                    values[f"velocity_OFF_{i}"] = 6.0
            create_session(date(2027, 1, 1), session_type, values)
        view = StatisticsView()
        self.assertEqual(self.distances(view)[-3:], [
            ["Seuil", "3,0 km"], ["VO2max", "4,0 km"], ["Total", "7,0 km"],
        ])
        self.assertEqual([row[3] for row in self.rows(view)[-3:]], [
            "300 m", "400 m", "700 m",
        ])

    def test_elevation_prefers_recorded_values_and_falls_back_to_incline(self: Self) -> None:
        """Verify recorded elevation, including zero, overrides incline estimates."""
        day = date(2027, 1, 1)
        self.save(day, distance="10.0", inclination=Decimal(5))
        self.save(day, distance="10.0", inclination=Decimal(5), elevation_gain=120)
        self.save(day, distance="10.0", inclination=Decimal(5), elevation_gain=0)
        self.save(day, distance="10.0")
        rows = self.rows(StatisticsView())
        self.assertEqual(rows[1][3], "620 m")
        self.assertEqual(rows[-1][3], "620 m")

    def test_zone_percentages_use_cumulative_durations_for_each_type_and_overall(self: Self) -> None:
        """Verify family and overall zone shares use cumulative recorded time."""
        day = date(2027, 1, 1)
        # Unequal session durations distinguish time weighting from averaging percentages.
        self.save(day, Z1=timedelta(minutes=10))
        self.save(day, Z2=timedelta(minutes=30))
        self.save(day, SessionType.LONG_RUN, Z3=timedelta(minutes=60))
        self.save(date(2027, 2, 1), Z5=timedelta(hours=10))
        rows = self.rows(StatisticsView())
        self.assertEqual(rows[0][4:], ["0 %", "0 %", "100 %", "0 %", "0 %"])
        self.assertEqual(rows[1][4:], ["25 %", "75 %", "0 %", "0 %", "0 %"])
        self.assertEqual(rows[2][4:], ["—"] * 5)
        self.assertEqual(rows[-1][4:], ["10 %", "30 %", "60 %", "0 %", "0 %"])

    def test_zone_percentages_include_durations_beyond_one_day(self: Self) -> None:
        """Verify zone shares include whole days rather than only residual seconds."""
        self.save(date(2027, 1, 1), Z4=timedelta(hours=30), Z5=timedelta(hours=10))
        rows = self.rows(StatisticsView())
        self.assertEqual(rows[-1][4:], ["0 %", "0 %", "0 %", "75 %", "25 %"])

    def test_duration_column_sums_endurance_sessions_and_overall(self: Self) -> None:
        """Verify endurance effort time appears before distance and sums by family."""
        day = date(2027, 1, 1)
        self.save(day, distance="10.0", velocity=Decimal("12.0"))
        self.save(day, distance="5.0", velocity=Decimal("10.0"))
        self.save(day, SessionType.STEADY_RUN, distance="7.5", velocity=Decimal("15.0"))
        self.save(day, SessionType.LONG_RUN, distance="30.0", velocity=Decimal("10.0"))
        view = StatisticsView()
        table = next(control for control in walk(view) if isinstance(control, ft.DataTable))
        self.assertEqual([cast(ft.Text, column.label).value for column in table.columns][:3], [
            "Type de séance", "Durée", "Distance",
        ])
        self.assertEqual([row[1] for row in self.rows(view)], [
            "03:00:00", "01:20:00", "00:30:00", "00:00:00", "00:00:00", "04:50:00",
        ])

    def test_empty_statistics_keep_all_columns_and_a_bold_overall_row(self: Self) -> None:
        """Verify an empty period retains the schema, placeholders and total style."""
        view = StatisticsView()
        table = self.table(view)
        self.assertEqual([cast(ft.Text, column.label).value for column in table.columns], [
            "Type de séance", "Durée", "Distance", "Dénivelé",
            "% Z1", "% Z2", "% Z3", "% Z4", "% Z5",
        ])
        self.assertEqual([column.numeric for column in table.columns], [False] + [True] * 8)
        self.assertEqual(len(table.rows), 6)
        for row in self.rows(view):
            self.assertEqual(row[1:], ["00:00:00", "0,0 km", "0 m"] + ["—"] * 5)
        self.assertTrue(all(cast(ft.Text, cell.content).weight == ft.FontWeight.BOLD for cell in table.rows[-1].cells))
        self.assertTrue(all(cast(ft.Text, cell.content).weight is None for cell in table.rows[0].cells))

    def test_refresh_preserves_period_and_table_while_reloading_measurements(self: Self) -> None:
        """Verify refresh retains controls and selection without sending an update."""
        self.save(date(2027, 1, 1))
        view = StatisticsView()
        self.select(view, "week")
        table = self.table(view)
        columns = tuple(table.columns)
        self.save(date(2027, 1, 2), distance="2.3")
        with patch.object(view, "update") as update:
            view.refresh()
        update.assert_not_called()
        self.assertIs(self.table(view), table)
        self.assertTrue(all(left is right for left, right in zip(table.columns, columns, strict=True)))
        self.assertEqual(self.title(view), "Semaine 53 - 2026")
        self.assertEqual(self.distances(view)[-1], ["Total", "12,3 km"])

    def test_month_navigation_queries_exact_leap_year_boundaries(self: Self) -> None:
        """Verify month navigation handles leap February and crosses year boundaries."""
        with patch.object(statistics_view, "get_running_sessions_between", return_value=[]) as reader:
            view = StatisticsView()
            view.selected_month = (2028, 1)
            view._change_period(1)
            self.assertEqual(self.title(view), "Février 2028")
            reader.assert_called_with(date(2028, 2, 1), date(2028, 2, 29))
            view._change_period(-2)
            self.assertEqual(self.title(view), "Décembre 2027")
            reader.assert_called_with(date(2027, 12, 1), date(2027, 12, 31))

    def test_fractional_durations_and_elevation_round_after_accumulation(self: Self) -> None:
        """Verify fractional seconds and meters are rounded after summing sessions."""
        for _ in range(3):
            self.save(date(2027, 1, 1), distance="0.1", velocity=Decimal(900),
                      inclination=Decimal("0.4"))
        self.assertEqual(self.rows(StatisticsView())[-1][1:4], ["00:00:01", "0,3 km", "1 m"])

    def test_cumulative_duration_can_exceed_one_day(self: Self) -> None:
        """Verify cumulative hours do not wrap at the twenty-four-hour boundary."""
        self.save(date(2027, 1, 1), distance="150", velocity=Decimal(5))
        self.assertEqual(self.rows(StatisticsView())[-1][1], "30:00:00")


if __name__ == "__main__":
    unittest.main()
