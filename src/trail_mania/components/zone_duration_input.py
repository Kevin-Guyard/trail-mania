"""Whole-second heart-rate-zone duration entry without a 24-hour limit."""

import re
from dataclasses import field
from decimal import Decimal
from typing import Self

import flet as ft

from trail_mania.components.numeric_input import NumericInput


@ft.control
class ZoneDurationInput(NumericInput):
    """Collect a heart-rate-zone duration in HH:MM:SS format.

    Notes
    -----
    Starts at 00:00:00 and adjusts in whole-second steps. Hours require
    at least two digits and may exceed 23; minutes and seconds must be
    between 00 and 59. The public value is integer seconds rather than
    the minutes used by DurationInput. Empty input remains distinguishable
    from a zero duration during required-field validation.

    Three numeric fields keep the colons immutable. Two typed digits advance
    to the next group; leaving a group pads a single digit with a leading zero.
    """

    label: str = "Durée zone"
    decimals: int = 0
    step: Decimal = field(default=Decimal("1"), metadata={"skip": True})

    def init(self: Self) -> None:
        """Initialize the numeric stepper with a zero-duration display.

        Notes
        -----
        The shared numeric state stores exact seconds as Decimal values;
        the overridden value property exposes them as integers.
        """
        super().init()
        self._field.hint_text = "00:00:00"
        self._value = Decimal("0")
        self._format()

    def _build_value_field(self: Self) -> ft.Column:
        """Keep separators outside three independently editable numeric fields."""
        self._parts = [
            ft.TextField(
                value="00",
                hint_text=hint,
                tooltip=f"{self.label} — {name}",
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.NumbersOnlyInputFilter(),
                max_length=limit,
                counter="",
                text_align=ft.TextAlign.CENTER,
                text_size=20,
                color=ft.Colors.BLACK,
                border=ft.NoInputBorder(),
                content_padding=ft.Padding.symmetric(horizontal=0, vertical=12),
                on_focus=self._focus_part,
                on_change=self._edit_part,
                on_blur=self._commit_part,
                on_submit=self._submit_part,
            )
            for hint, name, limit in (
                ("HH", "heures", None),
                ("MM", "minutes", 2),
                ("SS", "secondes", 2),
            )
        ]
        self._parts_snapshot = tuple(part.value for part in self._parts)
        self._error_text = ft.Text(color=ft.Colors.RED, size=12, visible=False)
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Row(spacing=0, controls=[
                    self._parts[0], ft.Text(":", size=20, color=ft.Colors.BLACK),
                    self._parts[1], ft.Text(":", size=20, color=ft.Colors.BLACK),
                    self._parts[2],
                ]),
                self._error_text,
            ],
        )

    def _sync_parts(self: Self) -> None:
        """Read even pending client edits before validation or dirty checking."""
        # Retain the shared numeric input's canonical text for parsing and snapshots.
        parts = tuple(part.value for part in self._parts)
        if parts != self._parts_snapshot:
            self._field.value = (
                ":".join(value.zfill(2) for value in parts) if any(parts) else ""
            )
            self._parts_snapshot = parts

    def _show_error(self: Self) -> None:
        self._error_text.value = self._field.error or ""
        self._error_text.visible = bool(self._field.error)

    def _read(self: Self) -> bool:
        valid = super()._read()
        self._show_error()
        return valid

    def validate(self: Self, *, required: bool = False) -> bool:
        valid = super().validate(required=required)
        self._show_error()
        return valid

    def _focus_part(self: Self, event: ft.Event[ft.TextField]) -> None:
        """Select the current group so typing replaces its initial zeroes."""
        event.control.selection = ft.TextSelection(0, len(event.control.value))
        self.update()

    async def _edit_part(self: Self, event: ft.Event[ft.TextField]) -> None:
        self._read()
        self.update()
        index = next(i for i, part in enumerate(self._parts) if part is event.control)
        if len(event.control.value) == 2 and index < 2 and self._field.error is None:
            await self._parts[index + 1].focus()

    def _commit_part(self: Self, event: ft.Event[ft.TextField]) -> None:
        """Pad a group immediately when the user moves elsewhere."""
        event.control.value = event.control.value.zfill(2)
        self._read()
        self.update()

    async def _submit_part(self: Self, event: ft.Event[ft.TextField]) -> None:
        self._commit_part(event)
        index = next(i for i, part in enumerate(self._parts) if part is event.control)
        if index < 2:
            await self._parts[index + 1].focus()

    def _parse(self: Self) -> Decimal | None:
        """Parse a strict HH:MM:SS duration into total seconds.

        Returns
        -------
        decimal.Decimal or None
            Nonnegative whole seconds, or None when the field is empty.

        Raises
        ------
        ValueError
            If hours have fewer than two digits or the time format is invalid.
        """
        self._sync_parts()
        text = self._field.value.strip()
        if not text:
            return None
        match = re.fullmatch(r"([0-9]{2,}):([0-5][0-9]):([0-5][0-9])", text)
        if match is None:
            raise ValueError
        hours, minutes, seconds = map(int, match.groups())
        return Decimal(hours * 3600 + minutes * 60 + seconds)

    def _validation_message(self: Self) -> str:
        """Describe the required time format and valid minute/second ranges.

        Returns
        -------
        str
            French HH:MM:SS validation message.
        """
        return "Saisir une durée HH:MM:SS (minutes et secondes de 00 à 59)"

    def _format(self: Self) -> None:
        """Render total seconds as HH:MM:SS without wrapping at 24 hours.

        Notes
        -----
        A missing value clears the text. Hours expand beyond two digits as
        needed, while minutes and seconds always use two digits.
        """
        if self._value is None:
            self._field.value = ""
            for part in self._parts:
                part.value = ""
            self._parts_snapshot = ("", "", "")
            self._show_error()
            return
        hours, remainder = divmod(int(self._value), 3600)
        minutes, seconds = divmod(remainder, 60)
        self._field.value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        for part, value in zip(self._parts, self._field.value.split(":")):
            part.value = value
        self._parts_snapshot = tuple(part.value for part in self._parts)
        self._show_error()

    @property
    def value(self: Self) -> int | None:
        """Return the last validated duration in whole seconds.

        Returns
        -------
        int or None
            Nonnegative second count, or None for empty or invalid text.
        """
        return int(self._value) if self._value is not None else None
