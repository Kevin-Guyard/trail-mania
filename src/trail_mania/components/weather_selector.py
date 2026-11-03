"""Optional weather selection and conversion to canonical storage labels."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import (
    ChoiceSelector,
    selector_icon,
    selector_segment,
)
from trail_mania.session_types import Weather


def weather_icon(weather: Weather) -> ft.Control:
    """Build the weather pictogram shared by selectors and table cells.

    Parameters
    ----------
    weather : Weather
        Supported weather condition to represent.

    Returns
    -------
    ft.Control
        Fresh black icon, or a semantic group of wind and rain icons for
        combined weather. Both forms carry the canonical French label.
    """
    if weather == Weather.WIND_RAIN:
        return ft.Semantics(
            label=weather.label,
            tooltip=weather.label,
            content=ft.Row(
                tight=True,
                height=27,
                spacing=2,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    selector_icon(ft.Icons.AIR, "Vent", size=20),
                    selector_icon(ft.Icons.WATER_DROP_OUTLINED, "Pluie", size=20),
                ],
            ),
        )
    icon = {
        Weather.NORMAL: ft.Icons.WB_SUNNY_OUTLINED,
        Weather.WIND: ft.Icons.AIR,
        Weather.RAIN: ft.Icons.WATER_DROP_OUTLINED,
    }[weather]
    return selector_icon(icon, weather.label)


@ft.control
class WeatherSelector(ChoiceSelector):
    """Collect optional outdoor weather as a single choice.

    Notes
    -----
    Uses ChoiceSelector synchronization and reset behavior, with a weather
    heading. Display captions may differ from stored labels: value maps
    the selected stable key to the canonical French database label.
    """

    label: str = "Météo"

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Build normal, wind, rain and combined wind/rain options.

        Returns
        -------
        list of ft.Segment
            Fresh weather segments, including a combined icon for wind and rain.
        """
        return [
            selector_segment(weather, caption, weather_icon(weather))
            for weather, caption in (
                (Weather.NORMAL, "Normale"),
                (Weather.WIND, "Vent"),
                (Weather.RAIN, "Pluie"),
                (Weather.WIND_RAIN, "Vent & Pluie"),
            )
        ]

    @property
    def value(self: Self) -> str | None:
        """Translate the selected weather key into its persisted French label.

        Returns
        -------
        str or None
            Canonical weather label, or None when no weather is selected.
        """
        return Weather(self.selected).label if self.selected is not None else None
