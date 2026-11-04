"""Prefilled session editing using the same controls as session creation."""

from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft
from sqlalchemy.exc import SQLAlchemyError

from trail_mania.session_records import SessionRecord
from trail_mania.session_repository import update_session
from trail_mania.session_types import SessionType
from trail_mania.views.add_session._session_details import SessionDetailsForm, SessionEditState
from trail_mania.views.add_session._session_form import SessionForm


@ft.control
class SessionEditView(ft.Container):
    """Edit an existing session with confirmation and unsaved-change handling.

    Parameters
    ----------
    session : SessionRecord
        Stored record supplying the identity, configuration and initial values.
    session_type : SessionType
        Family matching the record.
    on_back : callable or None, optional
        Zero-argument callback returning to the unchanged detail record.
        Defaults to None.
    on_saved : callable or None, optional
        Callback receiving the updated record after commit; defaults to None.

    Attributes
    ----------
    form : SessionForm
        Prefilled form with locked terrain, slope, movement and format choices.

    Raises
    ------
    ValueError
        If the initial record does not match the requested family.

    Notes
    -----
    Saving requires confirmation. Returning with unsaved changes offers
    save, discard and continue actions. Validation and persistence failures
    leave the editor open; completed navigation invalidates old events.
    """

    session: SessionRecord = field(kw_only=True, metadata={"skip": True})
    session_type: SessionType = field(kw_only=True, metadata={"skip": True})
    on_back: Callable[[], None] | None = field(default=None, metadata={"skip": True})
    on_saved: Callable[[SessionRecord], None] | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Build the edit form and capture its initial comparison state.

        Raises
        ------
        ValueError
            If the record does not match the form's session family.

        Notes
        -----
        Flet calls this hook during construction. A stored configuration
        creates a complete details form immediately, including strength dates.
        The baseline snapshot does not validate or rewrite client text.
        """
        self.expand = True
        self._saving: bool = False
        self._closed: bool = False
        self._dialog: ft.AlertDialog | None = None
        self.form: SessionForm = SessionForm(
            session_type=self.session_type, initial_session=self.session,
            on_back=self._back, on_submit=self._save,
        )
        assert self.form.details_form is not None
        self._details: SessionDetailsForm = self.form.details_form
        self._initial_state: SessionEditState = self._details.edit_state()
        self.content = self.form

    def _back(self: Self) -> None:
        """Request a return, resolving any changes before leaving.

        Notes
        -----
        Unchanged or reverted values leave immediately. Otherwise a dialog
        offers save, discard or continued editing. Events during saving,
        after navigation or while another confirmation is open are ignored.
        """
        if self._saving or self._closed or self._dialog is not None:
            return
        if self._details.edit_state() != self._initial_state:
            dialog = ft.AlertDialog(
                modal=True,
                content=ft.Text("Des modifications n'ont pas été enregistrées"),
                actions=[
                    ft.TextButton("Enregistrer", on_click=lambda event: self._confirm_save(dialog)),
                    ft.TextButton("Ne pas enregistrer", on_click=lambda event: self._discard(dialog)),
                    ft.TextButton("Continuer à modifier", on_click=lambda event: self._close_dialog(dialog)),
                ],
            )
            self._show_dialog(dialog)
            return
        self._leave()

    def _leave(self: Self) -> None:
        """Invalidate editor events and notify the navigation owner.

        Notes
        -----
        The screen closes before invoking ``on_back``. No values are written.
        """
        self._closed = True
        if self.on_back is not None:
            self.on_back()

    def _message(self: Self, message: str) -> None:
        """Display validation or persistence feedback on the mounted page.

        Parameters
        ----------
        message : str
            User-facing French text shown in a snackbar.
        """
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    def _save(self: Self, form: SessionDetailsForm) -> None:
        """Ask for confirmation before validating and writing the active form.

        Parameters
        ----------
        form : SessionDetailsForm
            Form requesting submission; must belong to this active editor.

        Notes
        -----
        Disabled forms, missing identities, stale events and repeated
        requests while a confirmation is open do not create another dialog.
        """
        if not self._can_save(form):
            return
        dialog = ft.AlertDialog(
            modal=True,
            content=ft.Text("Confirmer la modification"),
            actions=[
                ft.TextButton("Confirmer", on_click=lambda event: self._confirm_save(dialog)),
                ft.TextButton("Annuler", on_click=lambda event: self._close_dialog(dialog)),
            ],
        )
        self._show_dialog(dialog)

    def _can_save(self: Self, form: SessionDetailsForm) -> bool:
        """Check the form's identity and the editor's submission guards.

        Parameters
        ----------
        form : SessionDetailsForm
            Candidate form requesting persistence.

        Returns
        -------
        bool
            True for this enabled form with a persistent record identity,
            while the editor is open, idle and without a confirmation dialog.
        """
        return (
            not self._saving and not self._closed and self._dialog is None
            and form is self._details and not form.submit_button.disabled
            and self.session.session_id is not None
        )

    def _show_dialog(self: Self, dialog: ft.AlertDialog) -> None:
        """Register a confirmation and display it with dismissal tracking.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Fresh confirmation to make active. Callers check that no dialog
            is already open before calling this method.
        """
        self._dialog = dialog
        dialog.on_dismiss = lambda event: self._dismiss_dialog(dialog)
        self.page.show_dialog(dialog)

    def _dismiss_dialog(self: Self, dialog: ft.AlertDialog) -> None:
        """Release a dialog already dismissed by the client.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Dismissed confirmation; ignored if another dialog has replaced it.
        """
        if self._dialog is dialog:
            self._dialog = None

    def _close_dialog(self: Self, dialog: ft.AlertDialog) -> bool:
        """Close the current confirmation if its action is still applicable.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Confirmation requesting closure.

        Returns
        -------
        bool
            True after closing this active dialog. False for a stale dialog,
            an ongoing save or a closed editor.
        """
        # Dismissal and click events must only affect their own confirmation.
        if self._dialog is not dialog or self._saving or self._closed:
            return False
        self._dialog = None
        self.page.pop_dialog()
        return True

    def _confirm_save(self: Self, dialog: ft.AlertDialog) -> None:
        """Consume an active confirmation and persist the current inputs.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Save or unsaved-change confirmation authorizing the write.

        Notes
        -----
        Choosing save when leaving is itself confirmation; no second
        confirmation is opened. A stale dialog cannot authorize persistence.
        """
        if self._close_dialog(dialog):
            self._persist(self._details)

    def _discard(self: Self, dialog: ft.AlertDialog) -> None:
        """Consume the unsaved-change confirmation and leave without saving.

        Parameters
        ----------
        dialog : ft.AlertDialog
            Active confirmation offering to discard the pending changes.
        """
        if self._close_dialog(dialog):
            self._leave()

    def _persist(self: Self, form: SessionDetailsForm) -> None:
        """Validate and atomically save a confirmed edit.

        Parameters
        ----------
        form : SessionDetailsForm
            Active details form whose current inputs should be read.

        Notes
        -----
        Invalid fields and repository errors produce feedback without
        navigating or discarding inputs. Every attempt releases the save
        guard. Failed attempts re-enable submission; success keeps the old
        form disabled and passes the committed record to ``on_saved``.
        """
        session_id = self.session.session_id
        if not self._can_save(form) or session_id is None:
            return
        self._saving = True
        form.submit_button.disabled = True
        try:
            draft = form.read()
            if draft is None:
                self._message("Vérifie les champs indiqués avant d'enregistrer la séance.")
                return
            self.update()
            try:
                record = update_session(session_id, draft.date, draft.session_type, draft.detail_values)
            except (SQLAlchemyError, OSError):
                self._message("Impossible d'enregistrer les modifications. Réessaie.")
                return
            except ValueError as error:
                self._message(str(error))
                return
            self._closed = True
            if self.on_saved is not None:
                self.on_saved(record)
        finally:
            self._saving = False
            form.submit_button.disabled = self._closed
            if not self._closed:
                self.update()
