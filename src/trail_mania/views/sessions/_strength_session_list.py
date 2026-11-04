"""List leg-strength sessions using their recorded dates."""

from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft

from trail_mania.session_records import StrengthSession
from trail_mania.session_repository import get_strength_sessions
from trail_mania.session_types import SessionType


@ft.control
class StrengthSessionList(ft.Column):
    """Display stored leg-strength dates and open the selected record.

    Parameters
    ----------
    session_type : SessionType, optional
        Family identifier for navigation; keep the default LEG_STRENGTH.
    on_open_detail : callable or None, optional
        Callback receiving the selected StrengthSession; defaults to None.

    Attributes
    ----------
    table : ft.DataTable
        Single-column date table retaining duplicate sessions as separate rows.

    Notes
    -----
    Construction and explicit refreshes read storage. Each row callback
    retains its own record identity, even when several dates are equal.
    """

    session_type: SessionType = field(default=SessionType.LEG_STRENGTH, metadata={"skip": True})
    on_open_detail: Callable[[StrengthSession], None] | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Build the date table, empty-state message and initial rows.

        Notes
        -----
        Flet invokes this hook during construction. Initial loading delegates
        to ``refresh``; the owner mounts the completed control and updates it.
        """
        super().init()
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        self.table: ft.DataTable = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("Date", color=ft.Colors.BLACK))],
            show_checkbox_column=False,
        )
        self._empty_message: ft.Text = ft.Text("Aucune session de muscu jambes enregistrée.", color=ft.Colors.BLACK)
        self.controls = [self.table, self._empty_message]
        self.refresh()

    def refresh(self: Self) -> None:
        """Reload strength dates and rebuild their row callbacks.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If reading or converting the stored dates fails.
        OSError
            If the database storage directory cannot be accessed.

        Notes
        -----
        Rows are ordered by date then identity, both descending. The empty
        message is visible only without rows. The owner sends the client update.
        """
        self.table.rows = [ft.DataRow(
            cells=[ft.DataCell(ft.Text(session.date.strftime("%d/%m/%Y"), color=ft.Colors.BLACK))],
            on_select_change=(lambda event, record=session: self.on_open_detail(record))
            if self.on_open_detail is not None else None,
        ) for session in get_strength_sessions()]
        self._empty_message.visible = not self.table.rows
