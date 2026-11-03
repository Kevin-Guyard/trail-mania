"""Coordinate data loading, filtering and table rendering for one family."""

from dataclasses import field
from typing import Self

import flet as ft

from trail_mania.session_records import RecordedSession
from trail_mania.session_repository import get_sessions
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._filters import SessionFilters
from trail_mania.views.sessions._table import SessionTable


@ft.control
class SessionList(ft.Column):
    """Coordinate stored measurements, filter controls and their table.

    Parameters
    ----------
    session_type : SessionType, optional
        Running family to load; defaults to ``SessionType.EASY_RUN``.

    Attributes
    ----------
    filters : SessionFilters
        Persistent checkbox controls for the selected session family.
    table : SessionTable
        Scrollable presentation of the matching records.

    Notes
    -----
    Construction and explicit refreshes query storage. Checkbox changes only
    filter the loaded records. Python-side session metadata is excluded from
    Flet serialization.
    """

    session_type: SessionType = field(default=SessionType.EASY_RUN, metadata={"skip": True})

    def init(self: Self) -> None:
        """Build the controls and load the selected running family.

        Notes
        -----
        Flet calls this hook during construction. The owner mounts the
        completed list and sends its initial client update.
        """
        super().init()
        self.expand = True
        self.spacing = 0
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self.filters: SessionFilters = SessionFilters(
            session_type=self.session_type, on_change=self._on_filter_change,
        )
        self.table: SessionTable = SessionTable(session_type=self.session_type, filters=self.filters)
        self._sessions: list[RecordedSession] = []
        self.controls = [self.table]
        self.refresh()

    def refresh(self: Self) -> None:
        """Reload records and reapply the existing filter selection.

        See Also
        --------
        trail_mania.session_repository.get_sessions : Read the selected family.

        Notes
        -----
        Filter controls and measured column widths are retained. The owner
        sends the page update after this method completes.
        """
        self._sessions = get_sessions(self.session_type)
        self._apply_filters()

    def _on_filter_change(self: Self) -> None:
        """Filter the loaded records and send one enclosing client update.

        Notes
        -----
        No database query is made for checkbox changes.
        """
        self._apply_filters()
        self.update()

    def _apply_filters(self: Self) -> None:
        """Render matching records and the appropriate empty-state message.

        Notes
        -----
        A single immutable selection snapshot is shared by every predicate
        evaluation. The table consumes the matching records in storage order.
        """
        selection = self.filters.selection
        self.table.show_sessions(
            (session for session in self._sessions if selection.matches(session)),
            selection.empty_message,
        )
