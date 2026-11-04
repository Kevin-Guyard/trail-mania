"""Aggregate running measurements without storage or presentation concerns."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import cached_property
from types import MappingProxyType, NotImplementedType
from typing import Self, overload

from trail_mania.session_records import (
    EnduranceSession,
    RunningSession,
    calculate_zone_percentages,
)
from trail_mania.session_types import SessionType


def session_distance(session: RunningSession) -> Decimal:
    """Return kilometers, counting only recorded ON speeds for intervals.

    Parameters
    ----------
    session : EnduranceSession or IntervalSession
        Running measurements whose distance should be calculated.

    Returns
    -------
    Decimal
        Recorded endurance distance, or ON duration multiplied by the sum
        of recorded ON speeds and converted from minutes to hours.

    Notes
    -----
    ON durations are minutes and speeds are kilometers per hour. Missing
    distance or ON duration contributes zero. Missing ON speeds are skipped;
    recorded zero speeds remain values. Recovery phases are excluded.
    Arithmetic uses the active decimal context without display rounding.
    """
    if isinstance(session, EnduranceSession):
        return session.distance if session.distance is not None else Decimal(0)
    duration = session.duration_on if session.duration_on is not None else Decimal(0)
    # Convert through text to avoid importing float representation artifacts.
    speeds = sum(
        (Decimal(str(speed)) for speed in session.velocity_on if speed is not None),
        Decimal(0),
    )
    return duration * speeds / 60


def session_duration_seconds(session: RunningSession) -> Decimal:
    """Return effort time in seconds, excluding interval recovery phases.

    Parameters
    ----------
    session : EnduranceSession or IntervalSession
        Running measurements whose effort duration should be calculated.

    Returns
    -------
    Decimal
        Endurance distance divided by average speed and converted to
        seconds, or ON duration multiplied by the inferred repetition count
        and converted to seconds. Returns zero for missing distance, missing
        or nonpositive endurance speed, or missing ON duration.

    Notes
    -----
    A continuous threshold session counts as one effort. Interval duration
    includes every repetition of the inferred format, even when some ON
    speeds are missing. This differs from distance, which uses only recorded
    speeds. Zone durations do not determine effort time.
    """
    if isinstance(session, EnduranceSession):
        if session.distance is None or session.velocity is None or session.velocity <= 0:
            return Decimal(0)
        return session.distance / session.velocity * 3600
    duration = session.duration_on if session.duration_on is not None else Decimal(0)
    return duration * (session.session_format.repetitions or 1) * 60


@dataclass(frozen=True)
class SessionTotals:
    """Store cumulative running measurements before display rounding.

    Parameters
    ----------
    distance : Decimal, optional
        Cumulative distance in kilometers; defaults to zero.
    duration_seconds : Decimal, optional
        Cumulative effort time in seconds, possibly fractional; defaults
        to zero. Interval recovery time is excluded.
    elevation_gain : Decimal, optional
        Recorded or estimated cumulative elevation gain in meters; defaults
        to zero.
    zone_durations : tuple of datetime.timedelta, optional
        Five cumulative durations in Z1-to-Z5 order; defaults to five zero
        durations. Individual values may exceed one day.

    Notes
    -----
    Instances are immutable and support addition. Decimal arithmetic follows
    the active context; formatting and display rounding belong to the view.
    Constructor arguments are expected to satisfy the documented units and
    five-zone shape, without additional validation.
    """

    distance: Decimal = Decimal(0)
    duration_seconds: Decimal = Decimal(0)
    elevation_gain: Decimal = Decimal(0)
    zone_durations: tuple[timedelta, ...] = (timedelta(0),) * 5

    @classmethod
    def from_session(cls: type[Self], session: RunningSession) -> Self:
        """Calculate cumulative measurements for one running session.

        Parameters
        ----------
        session : EnduranceSession or IntervalSession
            Recorded measurements to convert into totals.

        Returns
        -------
        Self
            New totals containing the session's distance, effort duration,
            elevation gain and recorded zone durations.

        Notes
        -----
        Recorded elevation gain takes precedence, including zero. Otherwise,
        distance and incline percentage estimate elevation in meters. Missing
        elevation and incline contribute zero. Distance and duration use the
        same recovery exclusions as the corresponding calculation functions.
        """
        distance = session_distance(session)
        elevation = Decimal(0)
        if session.elevation_gain is not None:
            elevation = Decimal(session.elevation_gain)
        elif session.inclination is not None:
            # Convert kilometers to meters, then apply the incline percentage.
            elevation = distance * 1000 * session.inclination / 100
        return cls(
            distance=distance,
            duration_seconds=session_duration_seconds(session),
            elevation_gain=elevation,
            zone_durations=session.zone_durations,
        )

    @overload
    def __add__(self: Self, other: SessionTotals) -> SessionTotals: ...

    @overload
    def __add__(self: Self, other: object) -> SessionTotals | NotImplementedType: ...

    def __add__(self: Self, other: object) -> SessionTotals | NotImplementedType:
        """Combine two totals without mutating either operand.

        Parameters
        ----------
        other : object
            Another SessionTotals instance to add component by component.

        Returns
        -------
        SessionTotals or types.NotImplementedType
            New cumulative measurements, or NotImplemented when the other
            operand is not a SessionTotals instance.

        Raises
        ------
        ValueError
            If the operands contain different numbers of zone durations.

        Notes
        -----
        Raw zone durations are added before computing their percentages.
        No display rounding is applied during addition.
        """
        if not isinstance(other, SessionTotals):
            return NotImplemented
        return SessionTotals(
            distance=self.distance + other.distance,
            duration_seconds=self.duration_seconds + other.duration_seconds,
            elevation_gain=self.elevation_gain + other.elevation_gain,
            zone_durations=tuple(
                left + right
                for left, right in zip(self.zone_durations, other.zone_durations, strict=True)
            ),
        )

    @cached_property
    def zone_percentages(self: Self) -> tuple[float | None, ...]:
        """Calculate each zone's share of cumulative recorded zone time.

        Returns
        -------
        tuple of float or None
            Unrounded percentages in Z1-to-Z5 order. All five entries are
            None when the cumulative zone duration is zero.

        Notes
        -----
        Shares use cumulative zone time rather than effort duration or an
        average of per-session percentages. The result is cached because
        totals are immutable.
        """
        return calculate_zone_percentages(self.zone_durations)


@dataclass(frozen=True)
class SessionStatistics:
    """Store family totals and their overall total as one statistics snapshot.

    Parameters
    ----------
    by_type : mapping of SessionType to SessionTotals
        Running-family totals in display order, including empty families.
    overall : SessionTotals
        Sum of all running-family totals before display rounding.

    Notes
    -----
    The instance's fields cannot be reassigned. Snapshots created by
    summarize_sessions also wrap the family mapping in a read-only proxy.
    """

    by_type: Mapping[SessionType, SessionTotals]
    overall: SessionTotals


def summarize_sessions(sessions: Iterable[tuple[SessionType, RunningSession]]) -> SessionStatistics:
    """Aggregate each running family in one pass, retaining empty families.

    Parameters
    ----------
    sessions : iterable of (SessionType, RunningSession)
        Compatible running-family and measurement pairs for the period.
        May be a single-use iterator; duplicate records count separately.

    Returns
    -------
    SessionStatistics
        Read-only family mapping in SessionType declaration order, with zero
        totals for empty running families, and the sum of all family totals.

    Raises
    ------
    KeyError
        If a supplied family has no running measurements, such as leg strength.

    Notes
    -----
    The caller selects the date range and supplies compatible family/record
    pairs. Endurance records carry no family of their own, so each pair keeps
    that information explicit. The overall row sums family totals without
    recalculating individual sessions or averaging zone percentages.
    """
    totals: dict[SessionType, SessionTotals] = {
        session_type: SessionTotals() for session_type in SessionType if session_type.has_details
    }
    for session_type, session in sessions:
        totals[session_type] += SessionTotals.from_session(session)
    return SessionStatistics(
        by_type=MappingProxyType(totals),
        overall=sum(totals.values(), SessionTotals()),
    )
