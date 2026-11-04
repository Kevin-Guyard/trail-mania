"""Local-calendar session date selection and future-date validation."""

from datetime import date, datetime
from typing import Self

import flet as ft

from trail_mania.components.field_layout import field_column


@ft.control
class DateSelector(ft.Container):
    """Select a session's local calendar date, initially today.

    Notes
    -----
    The date picker uses French labels and disallows future dates.
    Timezone-aware values returned by Flet are converted to the local
    calendar day before their time component is removed.
    """

    def init(self: Self) -> None:
        """Initialize today's date and build the labeled date-picker button.

        Notes
        -----
        Flet calls this hook during construction. The visible date uses
        day/month/year formatting and is stored as a datetime.date.
        """
        self._selected_date: date = date.today()
        self._date_text: ft.Text = ft.Text(
            self._selected_date.strftime("%d/%m/%Y"),
            color=ft.Colors.BLACK,
            text_align=ft.TextAlign.CENTER,
        )
        self.content = field_column(
            "Date",
            ft.Button(
                content=self._date_text,
                icon=ft.Icons.CALENDAR_MONTH,
                height=56,
                style=ft.ButtonStyle(
                    shape=ft.StadiumBorder(),
                    side=ft.BorderSide(1, ft.Colors.BLACK),
                    bgcolor=ft.Colors.WHITE,
                    color=ft.Colors.BLACK,
                ),
                on_click=self._open_picker,
            ),
        )

    def _open_picker(self: Self, event: ft.Event[ft.Button]) -> None:
        """Open a French date picker bounded by the current local date.

        Parameters
        ----------
        event : ft.Event[ft.Button]
            Click event supplied by Flet; its payload is unused.

        Notes
        -----
        The current date is recomputed whenever the picker opens, so the
        upper bound remains correct if the application stays open overnight.
        """
        today = date.today()
        self.page.show_dialog(
            ft.DatePicker(
                value=self._selected_date,
                current_date=today,
                last_date=today,
                locale=ft.Locale("fr", "FR"),
                help_text="Date de la session",
                cancel_text="Annuler",
                confirm_text="Valider",
                on_change=self._change_date,
            )
        )

    def _change_date(self: Self, event: ft.Event[ft.DatePicker]) -> None:
        """Accept a selected date after local-time conversion and validation.

        Parameters
        ----------
        event : ft.Event[ft.DatePicker]
            Picker event containing a date, datetime or None when no date is selected.

        Notes
        -----
        Empty selections are ignored. Future dates restore the picker's
        previous value without changing the displayed session date. Aware
        datetimes use the local timezone; naive ones keep their calendar day.
        """
        value = event.control.value
        if value is None:
            return
        # Convert aware instants before dropping the time: local midnight
        # can be represented by the previous day in UTC.
        if isinstance(value, datetime):
            value = value.astimezone().date() if value.tzinfo is not None else value.date()
        if value > date.today():
            event.control.value = self._selected_date
            return
        self._selected_date = value
        self._date_text.value = self._selected_date.strftime("%d/%m/%Y")
        self.update()

    @property
    def selected(self: Self) -> date:
        """Return the selected local calendar day.

        Returns
        -------
        datetime.date
            Current calendar date, initially the construction day's local date.
        """
        return self._selected_date

    def set_value(self: Self, value: date) -> None:
        """Prefill a stored calendar date without emitting an update.

        Parameters
        ----------
        value : datetime.date
            Persisted calendar day to display in day/month/year format.

        Notes
        -----
        This setter trusts the stored date and does not apply the picker's
        future-date check. No callback or client update is emitted.
        """
        self._selected_date = value
        self._date_text.value = value.strftime("%d/%m/%Y")
