"""Render session details independently of list columns and navigation."""

from collections.abc import Callable, Iterable

import flet as ft

from trail_mania.components.elevation_selector import slope_icon
from trail_mania.components.movement_selector import movement_icon
from trail_mania.components.terrain_selector import terrain_icon
from trail_mania.components.weather_selector import weather_icon
from trail_mania.session_records import EnduranceSession, RecordedSession, SessionRecord, StrengthSession
from trail_mania.session_types import SESSION_FORMATS, LabeledChoice, Movement, Slope, Terrain, Weather
from trail_mania.views.sessions._formatting import MISSING, Measurement, format_measurement, measurement_text, text

type DetailRows = list[tuple[str, ft.Control]]


def heading(label: str) -> ft.Text:
    """Build a detail-section heading with the shared typography.

    Parameters
    ----------
    label : str
        Section caption to display.

    Returns
    -------
    ft.Text
        Fresh black, bold heading with a font size of 20.
    """
    return ft.Text(label, size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)


def detail_table(rows: DetailRows) -> ft.Row:
    """Build a two-column detail table with horizontal scrolling.

    Parameters
    ----------
    rows : list of tuple of (str, ft.Control)
        Labels and fresh value controls in the requested display order.

    Returns
    -------
    ft.Row
        Scrollable table sized to its content, with hidden headings and
        row heights that can grow to accommodate the value controls.

    Notes
    -----
    Value controls are attached directly to table cells and must not already
    belong to another Flet control tree.
    """
    return ft.Row(scroll=ft.ScrollMode.AUTO, controls=[ft.DataTable(
        show_bottom_border=True,
        horizontal_margin=12,
        column_spacing=28,
        columns=[ft.DataColumn(ft.Text("Variable")), ft.DataColumn(ft.Text("Valeur"))],
        heading_row_height=0,
        data_row_min_height=48,
        data_row_max_height=float("inf"),
        rows=[ft.DataRow(cells=[
            ft.DataCell(text(label)),
            ft.DataCell(ft.Container(content=value, padding=ft.Padding.symmetric(vertical=12))),
        ]) for label, value in rows],
    )])


def _choice[Choice: LabeledChoice](
    value: str | None, choices: Iterable[Choice], icon: Callable[[Choice], ft.Control],
) -> ft.Control:
    """Display a persisted choice as its pictogram and canonical label.

    Parameters
    ----------
    value : str or None
        Stored French label, or None for a missing or inapplicable choice.
    choices : iterable of LabeledChoice
        Supported members of one concrete choice enum.
    icon : callable
        Factory receiving the resolved choice and returning a fresh pictogram.

    Returns
    -------
    ft.Control
        Icon-and-label row, or an em-dash text control for an unknown or absent
        value. Unknown values do not call the icon factory.
    """
    choice = next((choice for choice in choices if choice.label == value), None)
    if choice is None:
        return text(MISSING)
    return ft.Row(tight=True, controls=[icon(choice), ft.Text(choice.label, color=ft.Colors.BLACK, no_wrap=True)])


def _location_rows(session: RecordedSession | StrengthSession) -> DetailRows:
    """Build date and applicable running-location rows.

    Parameters
    ----------
    session : RecordedSession or StrengthSession
        Record supplying a date and, for running, the stored location choices.

    Returns
    -------
    DetailRows
        Date row followed by terrain, slope and movement for running records.
        Movement is missing outside an inclined treadmill configuration.
    """
    rows: DetailRows = [("Date", text(session.date.strftime("%d/%m/%Y")))]
    if isinstance(session, RecordedSession):
        rows.extend([
            ("Terrain", _choice(session.terrain, Terrain, terrain_icon)),
            ("Pente", _choice(session.slope, Slope, slope_icon)),
            ("M / C", _choice(session.movement if session.requires_movement else None, Movement, movement_icon)),
        ])
    return rows


def _elevation_rows(session: RecordedSession) -> DetailRows:
    """Build inclination and elevation-gain rows with their units.

    Parameters
    ----------
    session : RecordedSession
        Running record supplying optional inclination and elevation gain.

    Returns
    -------
    DetailRows
        Inclination in percent and elevation gain in meters, preserving zeros
        and displaying absent measurements as em dashes.
    """
    return [
        ("Inclinaison", measurement_text(session.inclination, "%")),
        ("Dénivelé", measurement_text(session.elevation_gain, "m")),
    ]


def _conditions_rows(session: RecordedSession) -> DetailRows:
    """Build temperature, weather and perceived-exertion rows.

    Parameters
    ----------
    session : RecordedSession
        Running record supplying the optional conditions and RPE measurement.

    Returns
    -------
    DetailRows
        Temperature in degrees Celsius, weather pictogram and label, and RPE
        without a unit, in that order.
    """
    return [
        ("Température", measurement_text(session.temperature, "°C")),
        ("Météo", _choice(session.weather, Weather, weather_icon)),
        ("RPE", measurement_text(session.rpe)),
    ]


def _repetition(values: tuple[Measurement, ...], index: int, unit: str) -> str:
    """Format one measurement slot, including an absent trailing slot.

    Parameters
    ----------
    values : tuple of Measurement
        Measurements in repetition order.
    index : int
        Nonnegative, zero-based repetition index.
    unit : str
        Unit appended to a populated measurement.

    Returns
    -------
    str
        Formatted measurement or an em dash when the slot is absent or None.
    """
    return format_measurement(values[index] if index < len(values) else None, unit)


def measurement_rows(
    session: SessionRecord,
) -> tuple[DetailRows, DetailRows]:
    """Build the general and heart-rate rows for a recorded session.

    Parameters
    ----------
    session : SessionRecord
        Strength, endurance or supported interval record to render.

    Returns
    -------
    general : DetailRows
        Date and applicable running measurements in detail display order.
    heart : DetailRows
        Endurance heart-rate pair or one pair per interval storage slot.
        Empty for strength records.

    Notes
    -----
    Interval details show the family's maximum slot count regardless of the
    saved format. Shorter measurement tuples and unused recoveries remain
    visible as em dashes. Every call creates fresh value controls.
    """
    general = _location_rows(session)
    heart: DetailRows = []
    if isinstance(session, StrengthSession):
        return general, heart
    if isinstance(session, EnduranceSession):
        general.extend([
            ("Distance", measurement_text(session.distance, "km")),
            *_elevation_rows(session),
            ("Vitesse", measurement_text(session.velocity, "km/h")),
        ])
        heart.extend([
            ("FC moyenne", measurement_text(session.mean_hr, "bpm")),
            ("FC max", measurement_text(session.max_hr, "bpm")),
        ])
    else:
        general.extend([
            ("Durée ON", measurement_text(session.duration_on, "min")),
            ("Durée OFF", measurement_text(session.duration_off, "min")),
            *_elevation_rows(session),
        ])
        # Detail views show every storage slot, even when the saved format uses fewer.
        repetitions = max(choice.repetitions for choice in SESSION_FORMATS[session.session_type])
        for index in range(repetitions):
            general.append((f"Vitesse - rep {index + 1}", text(
                f"ON : {_repetition(session.velocity_on, index, 'km/h')} \u200a/ \u200a"
                f"OFF : {_repetition(session.velocity_off, index, 'km/h')}",
            )))
            heart.append((f"Rep {index + 1}", text(
                f"FC moy : {_repetition(session.mean_hr_on, index, 'bpm')} \u200a/ \u200a"
                f"FC max : {_repetition(session.max_hr_on, index, 'bpm')}",
            )))
    general.extend(_conditions_rows(session))
    return general, heart


def comment_section(comment: str) -> ft.Container:
    """Build the full, selectable comment section.

    Parameters
    ----------
    comment : str
        Complete stored comment, including any line breaks.

    Returns
    -------
    ft.Container
        Bordered comment card without line truncation. An empty comment uses
        a muted, italic French placeholder.
    """
    return ft.Container(
        padding=20,
        margin=ft.Margin.only(bottom=16),
        bgcolor=ft.Colors.WHITE,
        border=ft.Border.all(1, ft.Colors.GREY_300),
        border_radius=ft.BorderRadius.all(12),
        content=ft.Text(
            comment or "Aucun commentaire.", size=14,
            color=ft.Colors.BLACK if comment else ft.Colors.GREY_600,
            italic=not bool(comment), selectable=True, style=ft.TextStyle(height=1.5),
        ),
    )
