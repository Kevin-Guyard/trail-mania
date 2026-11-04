"""Measurement formatting shared by session tables and details."""

from decimal import Decimal
from typing import Final

import flet as ft

type Measurement = Decimal | float | int | None

MISSING: Final[str] = "—"


def format_measurement(value: Measurement, unit: str = "") -> str:
    """Format a stored measurement for French session displays.

    Parameters
    ----------
    value : Decimal, float, int or None
        Measurement to display. Zero is a value; None denotes missing data.
    unit : str, optional
        Unit appended after a space; defaults to an empty string.

    Returns
    -------
    str
        Decimal or float rounded for display to one decimal place with a
        comma separator; integers retain their precision. None yields an em
        dash without a unit. The input value is not modified.
    """
    if value is None:
        return MISSING
    number = format(value, ".1f") if isinstance(value, (Decimal, float)) else str(value)
    return f"{number.replace('.', ',')} {unit}".rstrip()


def text(value: str) -> ft.Text:
    """Create session text with the common foreground color.

    Parameters
    ----------
    value : str
        Already formatted caption or measurement.

    Returns
    -------
    ft.Text
        Fresh black text control inheriting the surrounding text style.
    """
    return ft.Text(value, color=ft.Colors.BLACK)


def measurement_text(value: Measurement, unit: str = "") -> ft.Text:
    """Render a formatted scalar independently of the table-column schema.

    Parameters
    ----------
    value : Decimal, float, int or None
        Stored measurement, including zero or an absent value.
    unit : str, optional
        Display unit; defaults to an empty string.

    Returns
    -------
    ft.Text
        Fresh black control containing the formatted measurement.

    See Also
    --------
    format_measurement : Decimal precision, units and missing-value handling.
    """
    return text(format_measurement(value, unit))
