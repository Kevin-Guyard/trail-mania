"""Shared session type picker for browsing and adding sessions."""

from collections.abc import Callable
from dataclasses import field
from typing import Final, Self

import flet as ft

from trail_mania.session_colors import SESSION_OPTIONS
from trail_mania.session_types import SessionType

_LABEL_HEIGHT: Final[int] = 64
_LABEL_SPACING: Final[int] = 12


@ft.control
class SessionTypePicker(ft.Column):
    """Display a centered, scrollable list of supported session types.

    Parameters
    ----------
    title : str, optional
        Heading displayed above the session types; defaults to "Ajouter une session".
    on_select : callable or None, optional
        Callback receiving the selected SessionType; defaults to None.
    excluded_types : tuple of SessionType, optional
        Types omitted from the list; defaults to an empty tuple.

    Notes
    -----
    The list order and colors come from SESSION_OPTIONS. Callback fields
    remain on the Python side and are excluded from Flet serialization.
    """

    title: str = "Ajouter une session"
    excluded_types: tuple[SessionType, ...] = field(default=(), metadata={"skip": True})
    on_select: Callable[[SessionType], None] | None = field(
        default=None,
        metadata={"skip": True},
    )

    def init(self: Self) -> None:
        """Build the title and height-bounded list during Flet initialization.

        Notes
        -----
        Bounding the scroll area lets the parent center the complete list
        while preserving scrolling on shorter screens.
        """
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        options = [option for option in SESSION_OPTIONS if option[0] not in self.excluded_types]
        labels = ft.Column(
            # Bound the scrollable list so its parent can center it vertically.
            height=len(options) * _LABEL_HEIGHT
            + max(0, len(options) - 1) * _LABEL_SPACING,
            spacing=_LABEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                self._session_label(session_type, color) for session_type, color in options
            ],
        )
        self.controls = [
            ft.Container(
                padding=ft.Padding.only(top=12),
                content=ft.Text(
                    self.title,
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLACK,
                    text_align=ft.TextAlign.CENTER,
                ),
            ),
            ft.Container(expand=True, alignment=ft.Alignment.CENTER, content=labels),
        ]

    def _session_label(self: Self, session_type: SessionType, color: ft.Colors) -> ft.Container:
        """Build the clickable label for one session type.

        Parameters
        ----------
        session_type : SessionType
            Type passed to the selection callback when clicked.
        color : ft.Colors
            Background color associated with this session type.

        Returns
        -------
        ft.Container
            Rounded, fixed-height label containing the session's French name.
        """
        def on_click(event: ft.Event[ft.Container]) -> None:
            """Forward a label click using its captured session type.

            Parameters
            ----------
            event : ft.Event[ft.Container]
                Click event emitted by this label; its payload is unused.
            """
            self._select(session_type)

        return ft.Container(
            height=_LABEL_HEIGHT,
            alignment=ft.Alignment.CENTER,
            bgcolor=color,
            border=ft.Border.all(1, ft.Colors.BLACK),
            border_radius=ft.BorderRadius.all(12),
            content=ft.Text(
                session_type,
                size=20,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
                text_align=ft.TextAlign.CENTER,
            ),
            on_click=on_click,
        )

    def _select(self: Self, session_type: SessionType) -> None:
        """Notify the owner that a session type has been selected.

        Parameters
        ----------
        session_type : SessionType
            Type selected by the user.
        """
        if self.on_select is not None:
            self.on_select(session_type)
