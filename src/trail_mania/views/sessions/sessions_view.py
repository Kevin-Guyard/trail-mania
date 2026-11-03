"""Navigate from session types to their recorded measurements."""

from typing import Self

import flet as ft

from trail_mania.components.session_type_picker import SessionTypePicker
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._session_list import SessionList


@ft.control
class SessionsView(ft.Container):
    """Navigate between running session types and their recorded measurements.

    Notes
    -----
    The active list and its filters survive application tab changes. Returning
    to the type picker discards that list. Strength sessions are omitted from
    the picker because they have no measurements to display.
    """

    def init(self: Self) -> None:
        """Initialize the type picker and navigation state.

        Notes
        -----
        Flet calls this hook during construction. No database query is made
        until a running session type is opened.
        """
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER
        self._session_list: SessionList | None = None
        self._session_choices: SessionTypePicker = SessionTypePicker(
            title="Sessions",
            excluded_types=(SessionType.LEG_STRENGTH,),
            on_select=self._open_session,
        )
        self.content = self._session_choices

    def _open_session(self: Self, session_type: SessionType | str) -> None:
        """Replace the picker with a fresh list and a navigation header.

        Parameters
        ----------
        session_type : SessionType or str
            Supported session family or its persisted French label.

        Raises
        ------
        ValueError
            If the label does not identify a supported session type.

        Notes
        -----
        Running sessions are loaded immediately with initially empty filters.
        Opening strength programmatically produces only the navigation header.
        The enclosing control is updated after the new content is installed.
        """
        session_type = SessionType(session_type)
        session_list: SessionList | None = (
            SessionList(session_type=session_type) if session_type.has_details else None
        )
        self._session_list = session_list
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
        if session_list is not None:
            content.controls.append(session_list)
        self.content = content
        self.update()

    def _on_back_click(self: Self, event: ft.Event[ft.IconButton]) -> None:
        """Handle the navigation header's back button.

        Parameters
        ----------
        event : ft.Event[ft.IconButton]
            Click event emitted by the back button; its payload is unused.
        """
        self._back_to_choices()

    def refresh(self: Self) -> None:
        """Reload the active list while preserving its filter controls.

        Notes
        -----
        This is a no-op while the type picker is visible. The application
        updates the page after activating the tab; this method does not send
        a separate client update.
        """
        if self._session_list is not None:
            self._session_list.refresh()

    def _back_to_choices(self: Self) -> None:
        """Discard the active list and restore the existing type picker.

        Notes
        -----
        A subsequent selection constructs fresh filters and reloads the data.
        The enclosing control is updated after the picker is restored.
        """
        self._session_list = None
        self.content = self._session_choices
        self.update()
