"""Compose session details and coordinate confirmed deletion."""

from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft
from sqlalchemy.exc import SQLAlchemyError

from trail_mania.session_records import SessionRecord, StrengthSession, validate_session_type
from trail_mania.session_repository import delete_session
from trail_mania.session_types import SessionType
from trail_mania.views.sessions._detail_sections import comment_section, detail_table, heading, measurement_rows
from trail_mania.views.sessions._zone_chart import zone_chart


@ft.control
class SessionDetailView(ft.Column):
    """Show a recorded session and coordinate its navigation and deletion.

    Parameters
    ----------
    session : SessionRecord
        Immutable running measurements or strength date to display.
    session_type : SessionType
        Family matching the record and used for the heading.
    on_back : callable or None, optional
        Zero-argument callback returning to the origin; defaults to None.
    on_deleted : callable or None, optional
        Callback after successful deletion. Falls back to ``on_back``.
    on_edit : callable or None, optional
        Callback opening the editor; defaults to None.
    back_tooltip : str, optional
        Back-button tooltip; defaults to the French session-list caption.

    Raises
    ------
    ValueError
        If the record's measurements do not match the session family.

    Notes
    -----
    Records without a persistent identity cannot be edited or deleted.
    Deletion requires confirmation. Failed writes keep that confirmation
    available for retry; completed navigation invalidates this screen's events.
    """

    session: SessionRecord = field(kw_only=True, metadata={"skip": True})
    session_type: SessionType = field(kw_only=True, metadata={"skip": True})
    on_back: Callable[[], None] | None = field(default=None, metadata={"skip": True})
    on_deleted: Callable[[], None] | None = field(default=None, metadata={"skip": True})
    on_edit: Callable[[], None] | None = field(default=None, metadata={"skip": True})
    back_tooltip: str = field(default="Retour à la liste des sessions", metadata={"skip": True})

    def init(self: Self) -> None:
        """Validate the record, initialize action guards and compose the view.

        Raises
        ------
        ValueError
            If the record and session family are incompatible.

        Notes
        -----
        Flet invokes this hook during construction. Building the sections
        does not read or write the database.
        """
        super().init()
        validate_session_type(self.session, self.session_type)
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self._delete_dialog: ft.AlertDialog | None = None
        self._deleting: bool = False
        self._closed: bool = False
        self.controls = self._build_sections()

    def _header(self: Self) -> ft.Row:
        """Build the title and the back and delete actions.

        Returns
        -------
        ft.Row
            Header with a disabled delete button for an unsaved record.
        """
        return ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
            ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=ft.Colors.BLACK,
                          tooltip=self.back_tooltip, on_click=self._go_back),
            ft.Text(self.session_type, size=28, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLACK, expand=True),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=28.8,
                icon_color=ft.Colors.WHITE,
                bgcolor=ft.Colors.RED_700,
                width=44,
                height=44,
                margin=ft.Margin.only(right=12),
                tooltip="Supprimer",
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
                disabled=self.session.session_id is None,
                on_click=self._ask_delete,
            ),
        ])

    def _build_sections(self: Self) -> list[ft.Control]:
        """Compose the sections appropriate to the record's measurements.

        Returns
        -------
        list of ft.Control
            Header, general information and edit action. Running records
            additionally include heart rates, zone shares and the full comment.
        """
        general, heart = measurement_rows(self.session)
        controls: list[ft.Control] = [self._header(), heading("Infos générales"), detail_table(general)]
        if not isinstance(self.session, StrengthSession):
            controls.extend([
                heading("Fréquence cardiaque"), detail_table(heart),
                heading("Zones"), zone_chart(self.session.zone_percentages),
                heading("Commentaire"), comment_section(self.session.comment),
            ])
        controls.append(self._edit_button())
        return controls

    def _edit_button(self: Self) -> ft.Row:
        """Build the centered edit action using the standard form layout.

        Returns
        -------
        ft.Row
            Button between equal spacers, disabled without a persistent ID.
        """
        return ft.Row(spacing=0, controls=[
            ft.Container(expand=1),
            ft.Button("Modifier", expand=1, disabled=self.session.session_id is None,
                      on_click=self._edit),
            ft.Container(expand=1),
        ])

    def _edit(self: Self, event: ft.Event[ft.Button]) -> None:
        """Close this detail screen and request its editor.

        Parameters
        ----------
        event : ft.Event[ft.Button]
            Button click supplied by Flet; its payload is unused.

        Notes
        -----
        An open deletion dialog, a missing identity or a closed screen
        prevents navigation. The screen closes before its callback runs.
        """
        if (not self._closed and self._delete_dialog is None
                and self.on_edit is not None and self.session.session_id is not None):
            self._closed = True
            self.on_edit()

    def _ask_delete(self: Self, event: ft.Event[ft.IconButton]) -> None:
        """Open a deletion confirmation without changing stored values.

        Parameters
        ----------
        event : ft.Event[ft.IconButton]
            Delete-button click; its payload is unused.

        Notes
        -----
        Only one confirmation may be open. Each action is bound to that
        dialog instance so delayed events cannot act on a later confirmation.
        """
        if self._delete_dialog is not None or self._closed or self.session.session_id is None:
            return
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Supprimer la séance ?"),
            content=ft.Text("Cette action est définitive"),
            actions=[
                ft.TextButton("Supprimer", style=ft.ButtonStyle(color=ft.Colors.RED_700),
                              on_click=lambda event: self._confirm_delete(dialog)),
                ft.TextButton("Annuler", on_click=lambda event: self._cancel_delete(dialog)),
            ],
        )
        dialog.on_dismiss = lambda event: self._dismiss_delete(dialog)
        self._delete_dialog = dialog
        self.page.show_dialog(dialog)

    def _cancel_delete(self: Self, dialog: ft.AlertDialog) -> None:
        """Close the active deletion confirmation without deleting anything.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Confirmation requesting cancellation.

        Notes
        -----
        Stale dialogs and cancellation during a write are ignored.
        """
        if self._delete_dialog is dialog and not self._deleting:
            self._delete_dialog = None
            self.page.pop_dialog()

    def _dismiss_delete(self: Self, dialog: ft.AlertDialog) -> None:
        """Release a confirmation already dismissed by the client.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Dialog whose native dismissal event was received.

        Notes
        -----
        This method does not pop the page's dialog stack. A replacement
        confirmation and an ongoing deletion remain unaffected.
        """
        if self._delete_dialog is dialog and not self._deleting:
            self._delete_dialog = None

    def _confirm_delete(self: Self, dialog: ft.AlertDialog) -> None:
        """Delete the identified session and notify its navigation owner.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Confirmation authorizing this deletion; must still be active.

        Notes
        -----
        The repository deletes the session and its details atomically.
        Database and filesystem failures are displayed in the same dialog
        and permit retry. Success closes the screen and dialog before calling
        ``on_deleted``, or ``on_back`` when no deletion callback is supplied.
        Duplicate and stale confirmations cannot repeat the write.
        """
        session_id = self.session.session_id
        # A cancelled dialog may emit a click after a new confirmation opens.
        if self._delete_dialog is not dialog or self._deleting or self._closed or session_id is None:
            return
        self._deleting = True
        try:
            delete_session(session_id)
        except (SQLAlchemyError, OSError):
            dialog.content = ft.Text(
                "Cette action est définitive\nImpossible de supprimer la séance. Réessaie.",
            )
            self.page.update()
            return
        finally:
            self._deleting = False
        self._closed = True
        self._delete_dialog = None
        self.page.pop_dialog()
        callback = self.on_deleted or self.on_back
        if callback is not None:
            callback()

    def _go_back(self: Self, event: ft.Event[ft.IconButton]) -> None:
        """Leave the detail screen through the origin's callback.

        Parameters
        ----------
        event : ft.Event[ft.IconButton]
            Back-button click supplied by Flet; its payload is unused.

        Notes
        -----
        Open confirmations block navigation. Closed screens and screens
        without a back callback ignore the event.
        """
        if not self._closed and self._delete_dialog is None and self.on_back is not None:
            self._closed = True
            self.on_back()
