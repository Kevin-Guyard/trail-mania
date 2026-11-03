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
            return
        hours, remainder = divmod(int(self._value), 3600)
        minutes, seconds = divmod(remainder, 60)
        self._field.value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def value(self: Self) -> int | None:
        """Return the last validated duration in whole seconds.

        Returns
        -------
        int or None
            Nonnegative second count, or None for empty or invalid text.
        """
        return int(self._value) if self._value is not None else None
