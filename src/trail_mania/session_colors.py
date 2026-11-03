"""Session palette shared by the picker and calendar cells."""

from typing import Final

import flet as ft

from trail_mania.session_types import SessionType


SESSION_OPTIONS: Final[tuple[tuple[SessionType, ft.Colors], ...]] = (
    (SessionType.LONG_RUN, ft.Colors.LIGHT_BLUE_300),
    (SessionType.EASY_RUN, ft.Colors.LIGHT_GREEN_300),
    (SessionType.STEADY_RUN, ft.Colors.YELLOW_600),
    (SessionType.THRESHOLD, ft.Colors.ORANGE_400),
    (SessionType.VO2MAX, ft.Colors.RED_400),
    (SessionType.LEG_STRENGTH, ft.Colors.GREY_500),
)
SESSION_COLORS: Final[dict[SessionType, ft.Colors]] = dict(SESSION_OPTIONS)
