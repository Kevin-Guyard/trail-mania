"""Immutable session measurements, independent of storage and UI controls."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property
from typing import Self

from trail_mania.session_types import (
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
    session_format_from_speeds,
)


@dataclass(frozen=True)
class StrengthSession:
    """Store a strength date and its optional persistent identity.

    Parameters
    ----------
    date : datetime.date
        Local calendar date without a time or timezone.
    session_id : int or None, optional
        Keyword-only persistent identity used for editing and deletion.
        Defaults to None for records not loaded from storage.

    Notes
    -----
    The record is immutable and retains no ORM or UI objects. Identity is
    excluded from measurement comparisons, so equal dates may still belong
    to different persisted sessions.
    """

    date: date
    session_id: int | None = field(default=None, kw_only=True, compare=False)


@dataclass(frozen=True)
class RecordedSession:
    """Store the immutable measurements shared by running session families.

    Parameters
    ----------
    date : datetime.date
        Local calendar date of the session, without a time or timezone.
    terrain : str
        Canonical French terrain label persisted by the repository.
    slope : str
        Canonical French slope label persisted by the repository.
    movement : str or None
        Canonical walking/running label for an inclined treadmill, or None.
    inclination : Decimal or None, optional
        Treadmill inclination in percent; defaults to None.
    elevation_gain : int or None, optional
        Cumulative elevation gain in meters; defaults to None.
    temperature : int or None, optional
        Ambient temperature in degrees Celsius; defaults to None.
    weather : str or None, optional
        Canonical French weather label; defaults to None.
    z1, z2, z3, z4, z5 : datetime.timedelta, optional
        Time spent in each heart-rate zone, with whole-second precision.
        Each defaults to zero duration and may exceed one day.
    rpe : Decimal or None, optional
        Rating of perceived exertion; defaults to None.
    comment : str, optional
        Free-text session comment; defaults to an empty string.
    session_id : int or None, optional
        Keyword-only persistent identity used for editing and deletion. Excluded from
        measurement comparisons; None for records not loaded from storage.

    Notes
    -----
    The repository supplies validated measurements. Records do not retain
    ORM objects or Flet controls, and do not validate constructor arguments.
    Missing measurements remain None; a numerical zero remains a value.
    """

    date: date
    terrain: str
    slope: str
    movement: str | None
    inclination: Decimal | None = None
    elevation_gain: int | None = None
    temperature: int | None = None
    weather: str | None = None
    z1: timedelta = timedelta(0)
    z2: timedelta = timedelta(0)
    z3: timedelta = timedelta(0)
    z4: timedelta = timedelta(0)
    z5: timedelta = timedelta(0)
    rpe: Decimal | None = None
    comment: str = ""
    session_id: int | None = field(default=None, kw_only=True, compare=False)

    @property
    def requires_movement(self: Self) -> bool:
        """Indicate whether walking and running distinguish this record.

        Returns
        -------
        bool
            True only for treadmill terrain combined with a hilly slope.
        """
        return self.terrain == Terrain.TREADMILL.label and self.slope == Slope.HILLY.label

    @cached_property
    def zone_percentages(self: Self) -> tuple[float | None, ...]:
        """Calculate each zone's share of total recorded zone duration.

        Returns
        -------
        tuple of float or None
            Five unrounded percentages in Z1-to-Z5 order. Every entry is None
            when the sum of zone durations is zero.

        Notes
        -----
        Timedelta division includes whole days. The result is cached for this
        immutable record; display rounding is left to the column renderer.
        """
        zones = (self.z1, self.z2, self.z3, self.z4, self.z5)
        total = sum(zones, timedelta(0))
        return tuple(zone / total * 100 if total else None for zone in zones)


@dataclass(frozen=True)
class EnduranceSession(RecordedSession):
    """Store distance-based measurements for a long, easy or steady run.

    Parameters
    ----------
    distance : Decimal or None, optional
        Distance in kilometers; defaults to None.
    velocity : Decimal or None, optional
        Average speed in kilometers per hour; defaults to None.
    mean_hr : int or None, optional
        Average heart rate in beats per minute; defaults to None.
    max_hr : int or None, optional
        Maximum heart rate in beats per minute; defaults to None.

    See Also
    --------
    RecordedSession : Inherited date, location and shared measurements.

    Notes
    -----
    The constructor also accepts every field documented by RecordedSession.
    """

    distance: Decimal | None = None
    velocity: Decimal | None = None
    mean_hr: int | None = None
    max_hr: int | None = None


@dataclass(frozen=True)
class IntervalSession(RecordedSession):
    """Store the work and recovery measurements of threshold or VO2max runs.

    Parameters
    ----------
    session_type : SessionType, optional
        Threshold or VO2max family; defaults to ``SessionType.THRESHOLD``.
    duration_on : Decimal or None, optional
        Duration of a work phase in minutes; defaults to None.
    duration_off : Decimal or None, optional
        Duration of a recovery phase in minutes; defaults to None.
    velocity_on : tuple of float or None, optional
        Work speeds in kilometers per hour. Defaults to three None entries.
    velocity_off : tuple of float or None, optional
        Intermediate recovery speeds in kilometers per hour. Defaults to two
        None entries; there is no recovery after the final work repetition.
    mean_hr_on : tuple of int or None, optional
        Average heart rate per work repetition, in beats per minute. Defaults
        to three None entries.
    max_hr_on : tuple of int or None, optional
        Maximum heart rate per work repetition, in beats per minute. Defaults
        to three None entries.

    See Also
    --------
    RecordedSession : Inherited date, location and shared measurements.

    Notes
    -----
    The constructor also accepts every field documented by RecordedSession.
    The repository pads work/heart-rate tuples to three slots for threshold
    and six for VO2max, and recovery tuples to one fewer slot. Unused values
    remain None. A continuous threshold effort occupies the first work slot.
    """

    session_type: SessionType = SessionType.THRESHOLD
    duration_on: Decimal | None = None
    duration_off: Decimal | None = None
    velocity_on: tuple[float | None, ...] = (None, None, None)
    velocity_off: tuple[float | None, ...] = (None, None)
    mean_hr_on: tuple[int | None, ...] = (None, None, None)
    max_hr_on: tuple[int | None, ...] = (None, None, None)

    @cached_property
    def session_format(self: Self) -> SessionFormat:
        """Infer the session format from the populated speed measurements.

        Returns
        -------
        SessionFormat
            Continuous or three-repetition threshold format, or a VO2max
            format with four, five or six repetitions.

        Raises
        ------
        ValueError
            If the record's family is neither threshold nor VO2max.

        Notes
        -----
        Zero speeds count as populated slots. The result is cached for this
        immutable record and uses the same rule as the calendar descriptions.
        """
        return session_format_from_speeds(self.session_type, self.velocity_on, self.velocity_off)


type RunningSession = EnduranceSession | IntervalSession
type SessionRecord = RunningSession | StrengthSession


def validate_session_type(session: RecordedSession | StrengthSession, session_type: SessionType) -> None:
    """Check that a record's measurement shape matches its session family.

    Parameters
    ----------
    session : RecordedSession or StrengthSession
        Record whose concrete subtype should be checked.
    session_type : SessionType
        Family requested by the form or detail view.

    Raises
    ------
    ValueError
        If strength or endurance measurements have an incompatible subtype,
        or an interval record carries a different interval family.

    Notes
    -----
    Endurance families share one measurement shape and are not distinguished
    within EnduranceSession. This function checks compatibility only; it
    does not validate individual measurements or access storage.
    """
    if session_type == SessionType.LEG_STRENGTH:
        matches = isinstance(session, StrengthSession)
    elif session_type.has_format:
        matches = isinstance(session, IntervalSession) and session.session_type == session_type
    else:
        matches = isinstance(session, EnduranceSession)
    if not matches:
        raise ValueError("Session measurements do not match the session type")
