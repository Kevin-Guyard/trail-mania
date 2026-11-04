"""Validated choices that determine which session fields are displayed."""

from dataclasses import dataclass
from typing import Self

from trail_mania.session_types import (
    SESSION_FORMATS,
    Movement,
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
)


@dataclass(frozen=True)
class SessionConfiguration:
    """Describe an immutable, complete running-session configuration.

    Parameters
    ----------
    session_type : SessionType
        Running session type; strength sessions have no configuration.
    terrain : Terrain
        Outdoor terrain or treadmill.
    slope : Slope
        Flat or hilly route.
    movement : Movement or None, optional
        Required only for an inclined treadmill; defaults to None.
    session_format : SessionFormat or None, optional
        Required for threshold and VO2max sessions only; defaults to None.

    Raises
    ------
    ValueError
        If the session type, movement or format combination is inconsistent.
    """

    session_type: SessionType
    terrain: Terrain
    slope: Slope
    movement: Movement | None = None
    session_format: SessionFormat | None = None

    def __post_init__(self: Self) -> None:
        """Reject incomplete or incompatible running-session choices.

        Raises
        ------
        ValueError
            If the type is strength, movement does not match the terrain and slope, or the format is unsupported.
        """
        if not self.session_type.has_details:
            raise ValueError("Strength sessions have no running configuration")
        needs_movement = self.terrain == Terrain.TREADMILL and self.slope == Slope.HILLY
        if needs_movement != (self.movement is not None):
            raise ValueError("Only inclined treadmill sessions require a movement")
        formats: tuple[SessionFormat | None, ...] = SESSION_FORMATS.get(self.session_type, (None,))
        if self.session_format not in formats:
            raise ValueError("Unsupported format for this session type")

    @property
    def repetitions(self: Self) -> int:
        """Return the number of work repetitions used by the form.

        Returns
        -------
        int
            Three to six for interval formats, or zero for continuous sessions.
        """
        return self.session_format.repetitions if self.session_format is not None else 0

    @property
    def outdoors(self: Self) -> bool:
        """Indicate whether outdoor measurement fields apply.

        Returns
        -------
        bool
            True for every terrain except the treadmill.
        """
        return self.terrain != Terrain.TREADMILL

    @property
    def detail_values(self: Self) -> dict[str, str | None]:
        """Translate the configuration into persisted detail-column values.

        Returns
        -------
        dict of str to str or None
            French terrain and slope labels, plus movement or None when inapplicable.
        """
        return {
            "field_type": self.terrain.label,
            "slope_type": self.slope.label,
            "dynamic_type": self.movement.label if self.movement is not None else None,
        }
