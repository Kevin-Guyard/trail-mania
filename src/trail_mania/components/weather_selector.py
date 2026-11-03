"""Optional weather selection and conversion to canonical storage labels."""

from typing import Self

import flet as ft

from trail_mania.components.choice_selector import (
    ChoiceSelector,
    selector_icon,
    selector_segment,
)
from trail_mania.session_types import Weather


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
            selector_segment(Weather.NORMAL, "Normale", ft.Icons.WB_SUNNY_OUTLINED),
            selector_segment(Weather.WIND, "Vent", ft.Icons.AIR),
            selector_segment(Weather.RAIN, "Pluie", ft.Icons.WATER_DROP_OUTLINED),
            selector_segment(
                Weather.WIND_RAIN,
                "Vent & Pluie",
                ft.Row(
                    tight=True,
                    height=27,
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        selector_icon(ft.Icons.AIR, "Vent", size=20),
                        selector_icon(ft.Icons.WATER_DROP_OUTLINED, "Pluie", size=20),
                    ],
                ),
            ),
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
