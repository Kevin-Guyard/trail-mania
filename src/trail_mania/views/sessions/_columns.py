"""Column definitions own ordering, formatting, sizing and alignment together."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Self, cast

import flet as ft

from trail_mania.components.elevation_selector import slope_icon
from trail_mania.components.movement_selector import movement_icon
from trail_mania.components.terrain_selector import terrain_icon
from trail_mania.components.weather_selector import weather_icon
from trail_mania.session_records import IntervalSession, RecordedSession
from trail_mania.session_types import (
    SESSION_FORMATS,
    LabeledChoice,
    Movement,
    SessionType,
    Slope,
    Terrain,
    Weather,
)

type Measurement = Decimal | float | None

_MISSING: Final[str] = "—"


def _text(value: str) -> ft.Text:
    """Create text using the table's foreground color.

    Parameters
    ----------
    value : str
        Formatted cell value, including any unit or missing-value marker.

    Returns
    -------
    ft.Text
        Fresh black text inheriting the table's text style.
    """
    return ft.Text(value, color=ft.Colors.BLACK)


def _measurement(value: Measurement, unit: str) -> ft.Text:
    """Format a measurement with a French decimal separator and optional unit.

    Parameters
    ----------
    value : Decimal, float, int or None
        Stored measurement. Integers keep their precision; Decimal and float
        values are displayed with one decimal place. None denotes missing data.
    unit : str
        Unit appended after a space; an empty string omits the unit.

    Returns
    -------
    ft.Text
        Formatted measurement or an em dash for missing data. Zero is preserved.
    """
    if value is None:
        return _text(_MISSING)
    number = format(value, ".1f") if isinstance(value, (Decimal, float)) else str(value)
    return _text(f"{number.replace('.', ',')} {unit}".rstrip())


@dataclass(frozen=True)
class SessionColumn:
    """Describe a column's heading, cell renderer and layout together.

    Parameters
    ----------
    label : str
        French heading displayed in the header.
    width : int
        Initial content width in logical pixels, excluding margins and spacing.
    render : callable
        Function receiving a compatible record and returning a fresh control.
    sample : str, optional
        Representative maximum-width value measured on the client alongside
        the heading. An empty string disables measurement; this is the default.
    alignment : ft.Alignment, optional
        Cell alignment; defaults to center right. Headings remain centered
        except for columns aligned center left.
    center_missing : bool, optional
        Whether an em-dash text placeholder is centered; defaults to False.

    Notes
    -----
    Renderers must create new controls for every cell, including duplicate
    records, because a Flet control cannot belong to multiple parents.
    """

    label: str
    width: int
    render: Callable[[RecordedSession], ft.Control]
    sample: str = ""
    alignment: ft.Alignment = field(default_factory=lambda: ft.Alignment.CENTER_RIGHT)
    center_missing: bool = False

    def cell(self: Self, session: RecordedSession, width: int) -> ft.DataCell:
        """Render one record using the column's current measured width.

        Parameters
        ----------
        session : RecordedSession
            Record compatible with this column's session family.
        width : int
            Current content width in logical pixels.

        Returns
        -------
        ft.DataCell
            Fresh cell containing a width-constrained, aligned control.
        """
        content = self.render(session)
        alignment = self.alignment
        if self.center_missing and isinstance(content, ft.Text) and content.value == _MISSING:
            alignment = ft.Alignment.CENTER
        return ft.DataCell(ft.Container(width=width, alignment=alignment, content=content))


def _measure_column(
    attribute: str,
    label: str,
    width: int,
    sample: str,
    unit: str = "",
    *,
    repetition: int | None = None,
    center_missing: bool = False,
) -> SessionColumn:
    """Define a column reading a numeric scalar or repetition measurement.

    Parameters
    ----------
    attribute : str
        Numeric record attribute supported by the selected session family.
    label : str
        French column heading.
    width : int
        Initial content width in logical pixels.
    sample : str
        Representative formatted value for client-side width measurement.
    unit : str, optional
        Measurement unit; defaults to an empty string.
    repetition : int or None, optional
        Zero-based tuple index for repeated measurements. None selects a
        scalar attribute; this is the default.
    center_missing : bool, optional
        Whether to center missing-value placeholders; defaults to False.

    Returns
    -------
    SessionColumn
        Numeric column with French formatting and right-aligned values.

    Notes
    -----
    The schema determines the compatible record subtype and attribute shape.
    Tuple entries beyond the supplied repetitions are displayed as missing.
    """
    def render(session: RecordedSession) -> ft.Text:
        """Read and format the configured measurement.

        Parameters
        ----------
        session : RecordedSession
            Record exposing the numeric attribute selected by the schema.

        Returns
        -------
        ft.Text
            Measurement text or an em dash for an absent repetition or value.
        """
        # The family-specific schema supplies numeric attributes and determines
        # whether the value is a scalar or a tuple of repetitions.
        if repetition is not None:
            values = cast(tuple[Measurement, ...], getattr(session, attribute))
            value: Measurement = values[repetition] if repetition < len(values) else None
        else:
            value = cast(Measurement, getattr(session, attribute))
        return _measurement(value, unit)

    return SessionColumn(label, width, render, sample, center_missing=center_missing)


def _icon_column[Choice: LabeledChoice](
    attribute: str,
    label: str,
    width: int,
    choices: Iterable[Choice],
    icon: Callable[[Choice], ft.Control],
) -> SessionColumn:
    """Define a centered pictogram column from persisted choice labels.

    Parameters
    ----------
    attribute : str
        Record attribute containing a canonical choice label or None.
    label : str
        French column heading.
    width : int
        Fixed content width in logical pixels.
    choices : iterable of LabeledChoice
        Supported members of one concrete choice enum.
    icon : callable
        Factory receiving a choice member and returning its fresh pictogram.

    Returns
    -------
    SessionColumn
        Centered column using an em dash for missing or unsupported choices.

    Notes
    -----
    Movement pictograms are suppressed outside inclined treadmill records.
    Labels are indexed once when the column is defined, rather than per cell.
    """
    by_label: dict[str, Choice] = {choice.label: choice for choice in choices}

    def render(session: RecordedSession) -> ft.Control:
        """Resolve the record's choice and build its pictogram.

        Parameters
        ----------
        session : RecordedSession
            Record exposing the configured choice attribute.

        Returns
        -------
        ft.Control
            Fresh pictogram or missing-value text.
        """
        value = cast(str | None, getattr(session, attribute))
        if attribute == "movement" and not session.requires_movement:
            value = None
        choice = by_label.get(value)
        return icon(choice) if choice is not None else _text(_MISSING)

    return SessionColumn(label, width, render, alignment=ft.Alignment.CENTER)


def _zone_column(index: int) -> SessionColumn:
    """Define a heart-rate zone percentage column.

    Parameters
    ----------
    index : int
        One-based zone number, from 1 through 5.

    Returns
    -------
    SessionColumn
        Right-aligned percentage column rounded to a whole percent.
    """
    def render(session: RecordedSession) -> ft.Text:
        """Format the selected zone's share of total zone duration.

        Parameters
        ----------
        session : RecordedSession
            Record providing the cached zone percentages.

        Returns
        -------
        ft.Text
            Whole percentage or an em dash when total duration is zero.
        """
        percentage = session.zone_percentages[index - 1]
        return _text(f"{percentage:.0f} %" if percentage is not None else _MISSING)

    return SessionColumn(f"% Z{index}", 65, render, "999 %")


def _comment(session: RecordedSession) -> ft.Text:
    """Render a comment with bounded visible text and its full tooltip.

    Parameters
    ----------
    session : RecordedSession
        Record carrying the optional free-text comment.

    Returns
    -------
    ft.Text
        At most two visible lines, with overflow ellipsis and the complete
        comment in a tooltip. Empty comments display an em dash.
    """
    return ft.Text(
        session.comment or _MISSING,
        color=ft.Colors.BLACK,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
        tooltip=session.comment or None,
    )


def _date(session: RecordedSession) -> ft.Text:
    """Format a session's local calendar date.

    Parameters
    ----------
    session : RecordedSession
        Record containing a date without a time or timezone.

    Returns
    -------
    ft.Text
        Date formatted as ``DD/MM/YYYY``.
    """
    return _text(session.date.strftime("%d/%m/%Y"))


def _format(session: RecordedSession) -> ft.Text:
    """Format the repetition count of an interval record.

    Parameters
    ----------
    session : RecordedSession
        IntervalSession record supplied by a family-specific column schema.

    Returns
    -------
    ft.Text
        Repetition caption such as ``x3``, or ``x1`` for continuous threshold.

    Notes
    -----
    The callable accepts the common record type to share the column interface;
    the interval schema guarantees the concrete subtype at runtime.
    """
    return _text(f"x{cast(IntervalSession, session).session_format.repetitions or 1}")


_LOCATION_COLUMNS: Final[tuple[SessionColumn, ...]] = (
    SessionColumn("Date", 100, _date,
                  alignment=ft.Alignment.CENTER),
    _icon_column("terrain", "Terrain", 60, Terrain, terrain_icon),
    _icon_column("slope", "Pente", 50, Slope, slope_icon),
    _icon_column("movement", "M / C", 50, Movement, movement_icon),
)
_ELEVATION_COLUMNS: Final[tuple[SessionColumn, ...]] = (
    _measure_column("inclination", "Incli", 70, "99,9 %", "%", center_missing=True),
    _measure_column("elevation_gain", "D+", 70, "99999 m", "m", center_missing=True),
)
_WEATHER_COLUMNS: Final[tuple[SessionColumn, ...]] = (
    _measure_column("temperature", "Temp", 80, "- 99 °C", "°C", center_missing=True),
    _icon_column("weather", "Météo", 60, Weather, weather_icon),
)
_EFFORT_COLUMNS: Final[tuple[SessionColumn, ...]] = (
    *(_zone_column(index) for index in range(1, 6)),
    _measure_column("rpe", "RPE", 55, "99,9"),
    SessionColumn("Commentaire", 280, _comment, alignment=ft.Alignment.CENTER_LEFT),
)


def columns_for(session_type: SessionType) -> tuple[SessionColumn, ...]:
    """Build an ordered schema for the requested running family.

    Parameters
    ----------
    session_type : SessionType
        Endurance, threshold or VO2max family to display.

    Returns
    -------
    tuple of SessionColumn
        Endurance columns or interval columns supporting the family's maximum
        repetition count, followed by shared effort measurements and comments.

    Raises
    ------
    ValueError
        If the family has no running-session details, such as leg strength.

    Notes
    -----
    Optional and unused measurements keep their columns and display em dashes.
    Recovery columns appear only between work repetitions.
    """
    if not session_type.has_details:
        raise ValueError("A running session type is required")
    if not session_type.has_format:
        return (
            *_LOCATION_COLUMNS,
            _measure_column("distance", "Dist", 80, "999,9 km", "km"),
            *_ELEVATION_COLUMNS,
            _measure_column("velocity", "Vit", 100, "99,9 km/h", "km/h"),
            *_WEATHER_COLUMNS,
            _measure_column("mean_hr", "FC moy", 90, "999 bpm", "bpm"),
            _measure_column("max_hr", "FC max", 90, "999 bpm", "bpm"),
            *_EFFORT_COLUMNS,
        )
    repetitions = max(choice.repetitions for choice in SESSION_FORMATS[session_type])
    speeds: list[SessionColumn] = []
    heart_rates: list[SessionColumn] = []
    for index in range(repetitions):
        speeds.append(_measure_column(
            "velocity_on", f"Vit ON {index + 1}", 100, "99,9 km/h", "km/h", repetition=index,
        ))
        # Recovery columns exist only between work repetitions.
        if index < repetitions - 1:
            speeds.append(_measure_column(
                "velocity_off", f"Vit OFF {index + 1}", 100, "99,9 km/h", "km/h", repetition=index,
            ))
        for attribute, label in (("mean_hr_on", "FC moy"), ("max_hr_on", "FC max")):
            heart_rates.append(_measure_column(
                attribute, f"{label} ON {index + 1}", 110, "999 bpm", "bpm", repetition=index,
            ))
    return (
        *_LOCATION_COLUMNS,
        SessionColumn("Format", 100, _format,
                      sample=f"x{repetitions}", alignment=ft.Alignment.CENTER),
        _measure_column("duration_on", "Dur ON", 90, "99,9 min", "min"),
        _measure_column("duration_off", "Dur OFF", 90, "99,9 min", "min"),
        *_ELEVATION_COLUMNS,
        *speeds,
        *_WEATHER_COLUMNS,
        *heart_rates,
        *_EFFORT_COLUMNS,
    )
