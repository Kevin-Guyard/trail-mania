"""Navigate from session types to their recorded measurements."""

from typing import Self

import flet as ft

from trail_mania.components.session_type_picker import SessionTypePicker
from trail_mania.session_records import SessionRecord
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._filters import FilterSelection
from trail_mania.views.sessions._session_list import SessionList
from trail_mania.views.sessions._session_navigation import SessionNavigation
from trail_mania.views.sessions._strength_session_list import StrengthSessionList


@ft.control
class SessionsView(ft.Container):
    """Navigate between session types and their recorded measurements.

    Notes
    -----
    The active list and its filters survive application tab changes. Returning
    to the type picker discards that list. Strength sessions display dates.
    Detail and edit screens share one navigation lifecycle. Writes and tab
    refreshes while those screens are open defer list rebuilding until return.
    """

    def init(self: Self) -> None:
        """Initialize the type picker and navigation state.

        Notes
        -----
        Flet calls this hook during construction. No database query is made
        until a session family is opened.
        """
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER
        self._session_list: SessionList | StrengthSessionList | None = None
        self._list_content: ft.Column | None = None
        self._list_needs_reload: bool = False
        self._session_choices: SessionTypePicker = SessionTypePicker(
            title="Sessions",
            on_select=self._open_session,
        )
        self.content = self._session_choices

    def _open_session(
        self: Self, session_type: SessionType | str, *, filter_selection: FilterSelection | None = None,
    ) -> None:
        """Replace the picker with a fresh list and a navigation header.

        Parameters
        ----------
        session_type : SessionType or str
            Supported session family or its persisted French label.
        filter_selection : FilterSelection or None, optional
            Saved choices to restore when rebuilding after a change.

        Raises
        ------
        ValueError
            If the label does not identify a supported session type.

        Notes
        -----
        Running sessions are loaded immediately with empty or restored filters.
        Strength sessions display a date list without terrain filters.
        The enclosing control is updated after the new content is installed.
        """
        session_type = SessionType(session_type)
        session_list: SessionList | StrengthSessionList = (
            StrengthSessionList(on_open_detail=self._open_detail)
            if session_type == SessionType.LEG_STRENGTH else
            SessionList(
                session_type=session_type,
                on_open_detail=self._open_detail,
                filter_selection=filter_selection,
            )
        )
        self._session_list = session_list
        self._list_needs_reload = False
        content: ft.Column = ft.Column(
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            icon_color=ft.Colors.BLACK,
                            tooltip="Retour",
                            on_click=self._on_back_click,
                        ),
                        ft.Text(
                            session_type,
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLACK,
                            expand=True,
                        ),
                    ],
                ),
            ],
        )
        content.controls.append(session_list)
        self._list_content = content
        self.content = content
        self.update()

    def _open_detail(self: Self, session: SessionRecord) -> None:
        """Open the selected record while retaining the list and its filters.

        Parameters
        ----------
        session : SessionRecord
            Selected record matching the active list's family.

        Notes
        -----
        Only events received while the list is visible open a detail. A new
        navigation lifecycle handles editing and deletion without reloading
        the retained list before the user returns to it.
        """
        if self._session_list is None or self.content is not self._list_content:
            return
        SessionNavigation(
            session=session, session_type=self._session_list.session_type,
            show=self._show_session, on_back=self._back_to_list,
        ).open()

    def _show_session(self: Self, control: ft.Control) -> None:
        """Install a detail or edit screen supplied by the navigation lifecycle.

        Parameters
        ----------
        control : ft.Control
            Fresh screen to display before sending an enclosing client update.
        """
        self.content = control
        self.update()

    def _reload_list(self: Self) -> None:
        """Build a fresh list with saved choices and reset scroll geometry.

        Notes
        -----
        The detached table has already been unmounted by Flet. Reusing it
        while replacing its rows can send invalid client patches on remount.
        Running filters, including hidden movement choices, are restored into
        fresh controls before records are loaded. No active list is a no-op.
        """
        panel = self._session_list
        if panel is not None:
            selection = panel.filters.selection if isinstance(panel, SessionList) else None
            self._open_session(panel.session_type, filter_selection=selection)

    def _back_to_list(self: Self, changed: bool = False) -> None:
        """Restore the list, reloading it when its records may have changed.

        Parameters
        ----------
        changed : bool, optional
            Whether editing or deletion committed a write in the detail
            lifecycle; defaults to False.

        Notes
        -----
        A successful write or deferred tab refresh rebuilds the list while
        preserving filter selections. Otherwise the existing controls and
        their scroll geometry are reused. No active list is a no-op.
        """
        if changed or self._list_needs_reload:
            self._reload_list()
            return
        if self._list_content is not None:
            self.content = self._list_content
            self.update()

    def _on_back_click(self: Self, event: ft.Event[ft.IconButton]) -> None:
        """Handle the navigation header's back button.

        Parameters
        ----------
        event : ft.Event[ft.IconButton]
            Click event emitted by the back button; its payload is unused.
        """
        if self.content is self._list_content:
            self._back_to_choices()

    def refresh(self: Self) -> None:
        """Reload the visible list or defer rebuilding until the detail closes.

        Notes
        -----
        This is a no-op while the type picker is visible. The application
        updates the page after activating the tab; this method does not send
        a separate client update. While detail or editing is visible, only a
        reload flag changes; the detached list and pending inputs are untouched.
        """
        if self._session_list is not None:
            if self.content is self._list_content:
                self._session_list.refresh()
            else:
                # The table is detached while showing a detail or editor.
                # Rebuild it on return instead of patching unmounted rows.
                self._list_needs_reload = True

    def _back_to_choices(self: Self) -> None:
        """Discard the active list and restore the existing type picker.

        Notes
        -----
        A subsequent selection constructs fresh filters and reloads the data.
        The enclosing control is updated after the picker is restored.
        """
        self._session_list = None
        self._list_content = None
        self._list_needs_reload = False
        self.content = self._session_choices
        self.update()
