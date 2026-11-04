"""Render statistics with one ordered schema for headings and measurements."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Self

import flet as ft

from trail_mania.session_statistics import SessionStatistics, SessionTotals
from trail_mania.views._formatting import (
    format_duration,
    format_measurement,
    format_percentage,
)


@dataclass(frozen=True)
class StatisticsColumn:
    """Keep a numeric heading beside its totals formatter.

    Parameters
    ----------
    label : str
        French heading displayed for this measurement.
    format : callable
        Function accepting SessionTotals and returning a display string,
        including the measurement's unit and display rounding.
    """

    label: str
    format: Callable[[SessionTotals], str]


def _zone_column(index: int) -> StatisticsColumn:
    """Bind a zone number to its percentage heading and formatter.

    Parameters
    ----------
    index : int
        One-based heart-rate zone number, from 1 through 5.

    Returns
    -------
    StatisticsColumn
        Numeric column rendering the selected zone's share as a whole
        percentage, or an em dash when total zone time is zero.
    """
    return StatisticsColumn(
        f"% Z{index}",
        lambda totals: format_percentage(totals.zone_percentages[index - 1]),
    )


_COLUMNS: Final[tuple[StatisticsColumn, ...]] = (
    StatisticsColumn("Durée", lambda totals: format_duration(totals.duration_seconds)),
    StatisticsColumn("Distance", lambda totals: format_measurement(totals.distance, "km")),
    StatisticsColumn("Dénivelé", lambda totals: f"{totals.elevation_gain:.0f} m"),
    *(_zone_column(index) for index in range(1, 6)),
)


@ft.control
class StatisticsTable(ft.DataTable):
    """Display running-family totals with persistent headings and table layout.

    Attributes
    ----------
    columns : list of ft.DataColumn
        Session-family heading followed by duration, distance, elevation
        gain and the five zone-percentage headings. Initialization builds
        these columns from the shared measurement schema.

    Notes
    -----
    Family rows follow snapshot order and the final overall row is bold.
    set_statistics replaces rows without updating the client. The owning
    view retains this control and sends the enclosing update.
    """

    columns: list[ft.DataColumn] = field(default_factory=list)

    def init(self: Self) -> None:
        """Initialize headings and typography from the statistics column schema.

        Notes
        -----
        Flet invokes this hook during construction. Row heights, spacing and
        text styling match the session tables. Rows are supplied separately
        by set_statistics after measurements have been loaded.
        """
        self.columns = [
            ft.DataColumn(
                ft.Text(label, color=ft.Colors.BLACK),
                numeric=index > 0,
                heading_row_alignment=ft.MainAxisAlignment.CENTER,
            )
            for index, label in enumerate(("Type de séance", *(column.label for column in _COLUMNS)))
        ]
        self.show_checkbox_column = False
        self.heading_row_height = 56
        self.data_row_min_height = self.data_row_max_height = 48
        self.heading_text_style = ft.TextStyle(size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)
        self.data_text_style = ft.TextStyle(size=14, color=ft.Colors.BLACK)
        self.column_spacing = self.horizontal_margin = 24

    def set_statistics(self: Self, statistics: SessionStatistics) -> None:
        """Replace family rows and the bold overall row with a new snapshot.

        Parameters
        ----------
        statistics : SessionStatistics
            Ordered family totals and their precomputed overall total.

        Notes
        -----
        Only formatting occurs here; measurements and their overall total
        are computed outside the table. Headings remain in place and the
        owning view sends the client update.
        """
        self.rows = [
            self._row(session_type.value, totals)
            for session_type, totals in statistics.by_type.items()
        ] + [self._row("Total", statistics.overall, bold=True)]

    @staticmethod
    def _row(label: str, totals: SessionTotals, *, bold: bool = False) -> ft.DataRow:
        """Render one labeled row in the measurement schema's column order.

        Parameters
        ----------
        label : str
            Session-family name or overall-total caption.
        totals : SessionTotals
            Unrounded measurements to format for this row.
        bold : bool, optional
            Whether to emphasize every cell; defaults to False.

        Returns
        -------
        ft.DataRow
            Fresh text cells containing the label and eight measurements.

        Notes
        -----
        Each row receives its own text controls because Flet controls cannot
        belong to multiple parents, even when two rows have equal totals.
        """
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(value, weight=ft.FontWeight.BOLD if bold else None))
            for value in (label, *(column.format(totals) for column in _COLUMNS))
        ])
