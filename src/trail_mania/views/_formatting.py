"""French measurement formatting shared by session and statistics views."""

from decimal import Decimal
from typing import Final

import flet as ft

type Measurement = Decimal | float | int | None

MISSING: Final[str] = "—"


def format_duration(total_seconds: Decimal) -> str:
    """Round cumulative seconds and display a duration without a 24-hour limit.

    Parameters
    ----------
    total_seconds : Decimal
        Nonnegative effort duration in seconds, including any fractional part.

    Returns
    -------
    str
        Duration in HH:MM:SS format. Hours have at least two digits and may
        exceed 23; minutes and seconds are padded to two digits.

    Notes
    -----
    Rounding to whole seconds follows the active decimal context. Callers
    supply cumulative durations so rounding occurs after aggregation.
    """
    hours, remainder = divmod(int(total_seconds.to_integral_value()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_percentage(value: float | None) -> str:
    """Format a whole percentage or an undefined-share placeholder.

    Parameters
    ----------
    value : float or None
        Unrounded percentage, or None when total recorded zone time is zero.

    Returns
    -------
    str
        Percentage rounded to a whole number followed by a percent sign.
        None yields an em dash; zero remains a displayed percentage.
    """
    return f"{value:.0f} %" if value is not None else MISSING


def format_measurement(value: Measurement, unit: str = "") -> str:
    """Format a stored measurement for French measurement displays.

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
