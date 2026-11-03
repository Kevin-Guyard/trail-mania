"""Session choices shared by the form controls and persistence layer."""

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final, Self

type SessionInputValue = Decimal | int | str | None
type SessionDetailValue = Decimal | float | int | str | timedelta | None
type SessionDetailValues = dict[str, SessionDetailValue]


class SessionType(StrEnum):
    """Identify the supported session families by their persisted labels.

    Notes
    -----
    Values double as French display names and database enum values.
    The three endurance families store distance-based measurements;
    threshold and VO2max require a format; leg strength has no detail row.
    """

    LONG_RUN = "Sortie longue"
    EASY_RUN = "Endurance fondamentale"
    STEADY_RUN = "Endurance active"
    THRESHOLD = "Seuil"
    VO2MAX = "VO2max"
    LEG_STRENGTH = "Muscu jambes"

    @property
    def has_details(self: Self) -> bool:
        """Indicate whether this type requires a separate detail row.

        Returns
        -------
        bool
            False only for leg strength; True for all running sessions.
        """
        return self != SessionType.LEG_STRENGTH

    @property
    def has_format(self: Self) -> bool:
        """Indicate whether a session format must be selected.

        Returns
        -------
        bool
            True for threshold and VO2max sessions; False for other types.
        """
        return self in (SessionType.THRESHOLD, SessionType.VO2MAX)


class LabeledChoice(StrEnum):
    """Pair a stable selector key with a persisted French label.

    Parameters
    ----------
    key : str
        String enum value exchanged with Flet segmented controls.
    label : str or None, optional
        French label required when declaring members; omitted in key lookups.

    Attributes
    ----------
    label : str
        Persisted label associated with this enum member's key.

    Notes
    -----
    Subclasses declare members as (key, label) pairs. The empty base
    enum can be extended without coupling domain choices to Flet controls.
    """

    label: str

    def __new__(cls: type[Self], key: str, label: str | None = None) -> Self:
        """Construct a string enum member carrying its canonical label.

        Parameters
        ----------
        key : str
            Stable string stored as the enum member's value.
        label : str or None, optional
            French label required when declaring a new member.

        Returns
        -------
        Self
            New member of the concrete choice enum.

        Raises
        ------
        TypeError
            If a new member is declared without its French label.

        Notes
        -----
        Enum handles existing-member lookups without calling this creation
        hook. The optional label also lets type checkers accept those
        single-key lookups while member declarations still require a label.
        """
        if label is None:
            raise TypeError("Choice declarations require a French label")
        choice: Self = str.__new__(cls, key)
        choice._value_ = key
        choice.label = label
        return choice


class Terrain(LabeledChoice):
    """Identify outdoor terrain categories and treadmill sessions.

    Notes
    -----
    Stable keys are road, rolling, technical and treadmill. Each member
    provides the French label accepted by the detail tables' field_type.
    """

    ROAD = "road", "Route"
    ROLLING = "rolling", "Terrain roulant"
    TECHNICAL = "technical", "Terrain technique"
    TREADMILL = "treadmill", "Tapis"


class Slope(LabeledChoice):
    """Identify flat and hilly session profiles.

    Notes
    -----
    The flat and hilly keys map to the French slope_type labels. Hilly
    treadmill sessions additionally require a movement choice.
    """

    FLAT = "flat", "Sans pente"
    HILLY = "hilly", "Avec pente"


class Movement(LabeledChoice):
    """Identify walking and running on an inclined treadmill.

    Notes
    -----
    The walk and run keys map to persisted dynamic_type labels. Other
    terrain and slope combinations do not store a movement.
    """

    WALK = "walk", "Marche"
    RUN = "run", "Course"


class Weather(LabeledChoice):
    """Identify the optional weather conditions stored for outdoor sessions.

    Notes
    -----
    The normal, wind, rain and wind_rain keys have canonical French
    labels. User-facing captions may use different grammatical forms
    or capitalization without changing the persisted labels.
    """

    NORMAL = "normal", "Normal"
    WIND = "wind", "Vent"
    RAIN = "rain", "Pluie"
    WIND_RAIN = "wind_rain", "Vent & pluie"


class SessionFormat(LabeledChoice):
    """Identify continuous threshold efforts and interval repetition counts.

    Notes
    -----
    SESSION_FORMATS determines which members apply to each session
    family. Formats control the visible measurements and are not stored
    as a separate detail-table column.
    """

    CONTINUOUS = "continuous", "Continu"
    THREE_REPETITIONS = "three_repetitions", "3 répétitions"
    FOUR_REPETITIONS = "four_repetitions", "4 répétitions"
    FIVE_REPETITIONS = "five_repetitions", "5 répétitions"
    SIX_REPETITIONS = "six_repetitions", "6 répétitions"

    @property
    def repetitions(self: Self) -> int:
        """Return the number of work repetitions represented by this format.

        Returns
        -------
        int
            Zero for continuous efforts, otherwise three, four, five or six.
        """
        return {
            SessionFormat.CONTINUOUS: 0,
            SessionFormat.THREE_REPETITIONS: 3,
            SessionFormat.FOUR_REPETITIONS: 4,
            SessionFormat.FIVE_REPETITIONS: 5,
            SessionFormat.SIX_REPETITIONS: 6,
        }[self]


SESSION_FORMATS: Final[dict[SessionType, tuple[SessionFormat, ...]]] = {
    SessionType.THRESHOLD: (
        SessionFormat.CONTINUOUS,
        SessionFormat.THREE_REPETITIONS,
    ),
    SessionType.VO2MAX: (
        SessionFormat.FOUR_REPETITIONS,
        SessionFormat.FIVE_REPETITIONS,
        SessionFormat.SIX_REPETITIONS,
    ),
}
