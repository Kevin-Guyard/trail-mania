"""A measured table whose filters scroll away before its header sticks."""

from collections.abc import Callable, Iterable
from dataclasses import field
from functools import partial
from math import ceil
from typing import Final, Self, cast

import flet as ft

from trail_mania.session_records import RunningSession
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._columns import SessionColumn, columns_for

_COLUMN_SPACING: Final[int] = 24
_HORIZONTAL_MARGIN: Final[int] = 24
_HEADING_HEIGHT: Final[int] = 56
_ROW_HEIGHT: Final[int] = 48
_FONT_SIZE: Final[int] = 14


@ft.control
class SessionTable(ft.Column):
    """Display measured columns with scrolling filters and a sticky header.

    Parameters
    ----------
    session_type : SessionType, optional
        Running family defining the column schema; defaults to easy run.
    filters : ft.Control or None, optional
        Control displayed above the table and included in vertical scrolling.
        Defaults to None. It remains reachable through the rendered control
        tree despite being excluded as a separate serialized field.
    on_open_detail : callable or None, optional
        Callback receiving the row's running record on selection. Defaults to
        None, leaving rows without a navigation action.

    Notes
    -----
    Header and body share one horizontal viewport. The header moves within
    their stack only after the filters scroll out of view. Width measurements
    update both tables and every existing row. Supplying rows mutates controls;
    the owner sends the enclosing update after filtering or loading completes.
    """

    session_type: SessionType = field(default=SessionType.EASY_RUN, metadata={"skip": True})
    filters: ft.Control | None = field(default=None, metadata={"skip": True})
    on_open_detail: Callable[[RunningSession], None] | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Construct the empty tables, viewports and width-measurement probes.

        Notes
        -----
        Flet invokes this hook during construction. It initializes scroll
        state and layout only; the owning list supplies the records.
        """
        # Column initializes the metadata needed by nested expanding viewports.
        super().init()
        self.expand = True
        self.spacing = 0
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self._columns: tuple[SessionColumn, ...] = columns_for(self.session_type)
        self._column_widths: list[int] = [column.width for column in self._columns]
        self._scroll_offset: float = 0.0
        self._filters_height: float = 0.0
        self._table_header: ft.DataTable = self._build_table(heading_height=_HEADING_HEIGHT)
        self._table: ft.DataTable = self._build_table(heading_height=0)
        self._empty_message: ft.Text = ft.Text(color=ft.Colors.BLACK, text_align=ft.TextAlign.CENTER)
        self._filters_section: ft.Container = ft.Container(
            padding=ft.Padding.only(bottom=10),
            on_size_change=self._on_filters_size_change,
            content=self.filters,
        )
        # A shared stack keeps the header and rows synchronized horizontally.
        self._sticky_header: ft.Container = ft.Container(
            top=0,
            left=0,
            right=0,
            height=_HEADING_HEIGHT,
            bgcolor="#F5F5F5",
            content=self._table_header,
        )
        self._table_stack: ft.Stack = ft.Stack(
            width=self._table_width(),
            height=_HEADING_HEIGHT,
            controls=[
                ft.Container(top=_HEADING_HEIGHT, left=0, right=0, content=self._table),
                self._sticky_header,
            ],
        )
        self._horizontal_viewport: ft.Row = ft.Row(
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[self._table_stack],
        )
        self._rows_viewport: ft.Column = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            scroll_interval=10,
            on_scroll=self._on_vertical_scroll,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[self._filters_section, self._horizontal_viewport, self._empty_message],
        )
        self._column_measurements: ft.Container = self._build_measurements()
        self.controls = [self._rows_viewport, self._column_measurements]

    def show_sessions(self: Self, sessions: Iterable[RunningSession], empty_message: str) -> None:
        """Replace displayed rows and update the empty-state message.

        Parameters
        ----------
        sessions : iterable of RunningSession
            Matching records compatible with this table's family. The iterable
            is consumed once and its order is preserved.
        empty_message : str
            French guidance displayed only when the iterable contains no rows.

        Notes
        -----
        Filters and measured widths are retained. The header position is
        clamped to the new row count before a later client scroll event can
        arrive. The owner sends the client update after this method returns.
        """
        self._table.rows = [
            ft.DataRow(on_select_change=(
                lambda event, record=session: self.on_open_detail(record)
            ) if self.on_open_detail is not None else None, cells=[
                column.cell(session, width)
                for column, width in zip(self._columns, self._column_widths, strict=True)
            ])
            for session in sessions
        ]
        self._empty_message.value = empty_message
        self._empty_message.visible = not self._table.rows
        self._table_stack.height = _HEADING_HEIGHT + len(self._table.rows) * _ROW_HEIGHT
        # Filtering can shrink the stack before the client emits another scroll event.
        self._position_header(update=False)

    def _table_width(self: Self) -> int:
        """Calculate the complete table width from the current content widths.

        Returns
        -------
        int
            Sum of column widths, spacing between columns and both outer
            margins, in logical pixels.
        """
        return (
            sum(self._column_widths)
            + (len(self._columns) - 1) * _COLUMN_SPACING
            + 2 * _HORIZONTAL_MARGIN
        )

    def _build_table(self: Self, heading_height: int) -> ft.DataTable:
        """Build a header or body table from the shared column schema.

        Parameters
        ----------
        heading_height : int
            Heading row height in logical pixels. Zero hides the body table's
            heading while retaining its labels for column sizing.

        Returns
        -------
        ft.DataTable
            Empty table using fixed row heights and current column widths.
        """
        return ft.DataTable(
            show_checkbox_column=False,
            width=self._table_width(),
            columns=[
                ft.DataColumn(ft.Text(
                    column.label,
                    width=width,
                    color=ft.Colors.BLACK,
                    text_align=(
                        ft.TextAlign.LEFT if column.alignment == ft.Alignment.CENTER_LEFT
                        else ft.TextAlign.CENTER
                    ),
                ))
                for column, width in zip(self._columns, self._column_widths, strict=True)
            ],
            rows=[],
            heading_row_height=heading_height,
            data_row_min_height=_ROW_HEIGHT,
            data_row_max_height=_ROW_HEIGHT,
            heading_text_style=ft.TextStyle(size=_FONT_SIZE, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
            data_text_style=ft.TextStyle(size=_FONT_SIZE, color=ft.Colors.BLACK),
            column_spacing=_COLUMN_SPACING,
            horizontal_margin=_HORIZONTAL_MARGIN,
        )

    def _build_measurements(self: Self) -> ft.Container:
        """Build invisible probes for the client's rendered text dimensions.

        Returns
        -------
        ft.Container
            Zero-height clipped container with probes for columns that define
            a sample. Each probe measures its sample and bold heading together.

        Notes
        -----
        Client font metrics and text scaling determine the measured widths.
        Each callback is bound to its own schema index.
        """
        # Invisible probes still participate in layout, but occupy no page height.
        return ft.Container(
            height=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Row(
                opacity=0,
                scroll=ft.ScrollMode.HIDDEN,
                controls=[
                    ft.Stack(
                        controls=[
                            ft.Text(column.sample, size=_FONT_SIZE, weight=ft.FontWeight.NORMAL),
                            ft.Text(column.label, size=_FONT_SIZE, weight=ft.FontWeight.BOLD),
                        ],
                        on_size_change=partial(self._on_column_size, index=index),
                    )
                    for index, column in enumerate(self._columns)
                    if column.sample
                ],
            ),
        )

    def _on_column_size(self: Self, event: ft.LayoutSizeChangeEvent[ft.LayoutControl], index: int) -> None:
        """Apply a measured content width to both headings and existing cells.

        Parameters
        ----------
        event : ft.LayoutSizeChangeEvent[ft.LayoutControl]
            Probe size event carrying the rendered width in logical pixels.
        index : int
            Zero-based index of the measured column in the shared schema.

        Notes
        -----
        Widths are rounded upward to prevent clipping. Nonpositive or unchanged
        widths are ignored; other changes send one enclosing control update.
        """
        width = ceil(event.width)
        if width <= 0 or self._column_widths[index] == width:
            return
        self._column_widths[index] = width
        table_width = self._table_width()
        # The body also has hidden heading labels that determine column widths.
        for table in (self._table_header, self._table):
            cast(ft.Text, table.columns[index].label).width = width
            table.width = table_width
        for row in self._table.rows:
            cast(ft.Container, row.cells[index].content).width = width
        self._table_stack.width = table_width
        self.update()

    def _on_filters_size_change(self: Self, event: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        """Record the filter section's height and reposition the header.

        Parameters
        ----------
        event : ft.LayoutSizeChangeEvent[ft.LayoutControl]
            Filter container size event, including its bottom padding.
        """
        self._filters_height = event.height
        self._position_header()

    def _on_vertical_scroll(self: Self, event: ft.OnScrollEvent) -> None:
        """Track vertical scrolling and reposition the sticky header.

        Parameters
        ----------
        event : ft.OnScrollEvent
            Scroll notification whose pixel offset is relative to the start
            of the filter section. Negative overscroll is treated as zero.
        """
        self._scroll_offset = max(0.0, event.pixels)
        self._position_header()

    def _position_header(self: Self, *, update: bool = True) -> None:
        """Pin the header after the filters while keeping it inside the table.

        Parameters
        ----------
        update : bool, optional
            Whether a changed position immediately updates the header control;
            defaults to True. False lets the owner batch a larger update.

        Notes
        -----
        The offset stays zero until the filter section has scrolled away and
        cannot exceed the height of the remaining data rows.
        """
        top = min(
            max(0.0, self._scroll_offset - self._filters_height),
            len(self._table.rows) * _ROW_HEIGHT,
        )
        if self._sticky_header.top != top:
            self._sticky_header.top = top
            if update:
                self._sticky_header.update()
