"""One detail/edit lifecycle, independent of its list or calendar origin."""

from collections.abc import Callable
from typing import Self

import flet as ft

from trail_mania.session_records import SessionRecord
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._session_edit import SessionEditView
from trail_mania.views.sessions.session_detail_view import SessionDetailView


class SessionNavigation:
    """Show fresh screens and report whether the origin needs reloading.

    Parameters
    ----------
    session : SessionRecord
        Initial immutable record to display and edit.
    session_type : SessionType
        Family matching that record.
    show : callable
        Callback receiving the next detail or edit control. The owner installs
        it in its content and sends the client update.
    on_back : callable
        Callback receiving whether a save or deletion succeeded during this
        lifecycle, so the origin can decide whether to reload.
    back_tooltip : str, optional
        Detail back-button tooltip; defaults to the French session-list caption.

    Notes
    -----
    Screens close before navigating, rejecting delayed clicks on their old
    controls. Saving replaces the current record; cancelling keeps it.
    The origin receives control of refreshing only when the detail closes.
    Construction stores callbacks without displaying a screen; call ``open``
    to begin navigation.
    """

    def __init__(
        self: Self, session: SessionRecord, session_type: SessionType, *,
        show: Callable[[ft.Control], None], on_back: Callable[[bool], None],
        back_tooltip: str = "Retour à la liste des sessions",
    ) -> None:
        """Store the record and owner callbacks for a fresh navigation lifecycle.

        Notes
        -----
        Arguments are documented on the class. Initialization neither builds
        Flet screens nor accesses storage.
        """
        self._session: SessionRecord = session
        self._session_type: SessionType = session_type
        self._show: Callable[[ft.Control], None] = show
        self._on_back: Callable[[bool], None] = on_back
        self._back_tooltip: str = back_tooltip
        self._changed: bool = False

    def open(self: Self) -> None:
        """Display a fresh detail screen for the latest record.

        Raises
        ------
        ValueError
            If the record and requested family do not match.

        Notes
        -----
        Returning from editing preserves the lifecycle's change flag. A
        successful save supplies a new record before this screen is built.
        """
        self._show(SessionDetailView(
            session=self._session, session_type=self._session_type,
            on_back=self._back, on_edit=self._edit, on_deleted=self._deleted,
            back_tooltip=self._back_tooltip,
        ))

    def _edit(self: Self) -> None:
        """Display a prefilled editor bound to the current record.

        Notes
        -----
        Cancelling reconstructs the detail from the same record; saving
        replaces that record before returning to the detail.
        """
        self._show(SessionEditView(
            session=self._session, session_type=self._session_type,
            on_back=self.open, on_saved=self._saved,
        ))

    def _saved(self: Self, session: SessionRecord) -> None:
        """Remember committed measurements and reopen their detail.

        Parameters
        ----------
        session : SessionRecord
            Updated record returned by the successful persistence operation.
        """
        self._session = session
        self._changed = True
        self.open()

    def _deleted(self: Self) -> None:
        """Report a successful deletion and return to the origin.

        Notes
        -----
        The deleted record is never displayed again within this lifecycle.
        """
        self._changed = True
        self._back()

    def _back(self: Self) -> None:
        """Return to the owner with the lifecycle's accumulated change flag.

        Notes
        -----
        The owner preserves its filters or calendar period and decides how
        to reload. This method does not query storage or render the origin.
        """
        self._on_back(self._changed)
