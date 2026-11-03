"""Coordinate session selection, navigation and saving."""

import logging
from typing import Final, Self

import flet as ft
from sqlalchemy.exc import SQLAlchemyError

from trail_mania.session_repository import create_session
from trail_mania.session_types import SessionType
from trail_mania.views.add_session._session_details import SessionDetailsForm
from trail_mania.views.add_session._session_form import SessionForm
from trail_mania.views.add_session._session_picker import SessionTypePicker

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@ft.control
class AddSessionView(ft.Container):
    """Coordinate session selection, form navigation and atomic persistence.

    Notes
    -----
    The current form survives navigation to another application tab.
    Returning to the session picker discards it. Only the current
    details form may submit, preventing stale events from saving data.
    """

    def init(self: Self) -> None:
        """Initialize the picker, navigation state and submission guard.

        Notes
        -----
        Flet invokes this hook during control construction. No database
        connection is opened until a valid form is submitted.
        """
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER
        self._saving: bool = False
        self._form: SessionForm | None = None
        self._session_choices: SessionTypePicker = SessionTypePicker(on_select=self._open_session)
        self.content = self._session_choices

    def _open_session(self: Self, session_type: SessionType | str) -> None:
        """Replace the picker with a fresh form for the requested session type.

        Parameters
        ----------
        session_type : SessionType or str
            Supported session type or its persisted French label.

        Raises
        ------
        ValueError
            If the label does not identify a supported session type.
        """
        self._form = SessionForm(
            session_type=SessionType(session_type),
            on_back=self._back_to_choices,
            on_submit=self._submit_session,
        )
        self.content = self._form
        self.update()

    def _back_to_choices(self: Self) -> None:
        """Discard the current form and display the existing session picker.

        Notes
        -----
        Dropping the active form reference also invalidates delayed submit
        events from its controls. Ordinary tab changes do not call this method.
        """
        self._form = None
        self.content = self._session_choices
        self.update()

    def _submit_session(self: Self, form: SessionDetailsForm) -> None:
        """Validate and save the active form, then return to the picker.

        Parameters
        ----------
        form : SessionDetailsForm
            Details form requesting submission; discarded and disabled forms are ignored.

        Notes
        -----
        Validation errors and database or filesystem failures leave the form
        available for correction or retry. The repository rolls back failed
        writes. Successful forms keep their submit button disabled to reject
        duplicate clicks, and every attempt releases the submission guard.
        """
        # A queued click may refer to controls replaced by a later choice.
        if (
            self._saving
            or form.submit_button.disabled
            or self._form is None
            or self._form.details_form is not form
        ):
            return

        self._saving = True
        form.submit_button.disabled = True
        saved = False
        try:
            draft = form.read()
            if draft is None:
                self._show_save_message("Vérifie les champs indiqués avant d'ajouter la session.")
                return

            self.update()
            try:
                create_session(draft.date, draft.session_type, draft.detail_values)
            except (SQLAlchemyError, OSError):
                _LOGGER.exception("Could not save training session")
                self._show_save_message("Impossible d'enregistrer la session. Réessaie.")
                return

            saved = True
            self._back_to_choices()
            self._show_save_message("Session enregistrée.")
        finally:
            self._saving = False
            # Keep successful forms disabled; failed attempts remain retryable.
            form.submit_button.disabled = saved
            if not saved:
                self.update()

    def _show_save_message(self: Self, message: str) -> None:
        """Display validation or persistence feedback in a snackbar.

        Parameters
        ----------
        message : str
            User-facing French message to show on the mounted page.
        """
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))
