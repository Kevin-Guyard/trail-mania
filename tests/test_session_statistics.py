"""Unit coverage for running measurements and immutable statistics snapshots."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Self

from trail_mania.session_records import EnduranceSession, IntervalSession
from trail_mania.session_statistics import (
    SessionTotals,
    session_distance,
    session_duration_seconds,
    summarize_sessions,
)
from trail_mania.session_types import SessionType


class SessionStatisticsTests(unittest.TestCase):
    """Verify statistics calculations without database or Flet dependencies.

    Notes
    -----
    Each test derives records from empty endurance and interval fixtures so
    missing values, recorded zeroes and fractional measurements stay explicit.
    """

    def setUp(self: Self) -> None:
        """Create immutable session fixtures with absent optional measurements."""
        self.endurance: EnduranceSession = EnduranceSession(date(2027, 1, 1), "Route", "Sans pente", None)
        self.interval: IntervalSession = IntervalSession(date(2027, 1, 1), "Route", "Sans pente", None)

    def test_interval_distances_sum_on_repetitions_and_ignore_recovery(self: Self) -> None:
        """Verify interval distance uses only ON speeds and handles absent distance."""
        for session_type, repetitions in ((SessionType.THRESHOLD, 3), (SessionType.VO2MAX, 6)):
            with self.subTest(session_type=session_type):
                session = replace(
                    self.interval, session_type=session_type,
                    duration_on=Decimal(5), duration_off=Decimal(2),
                    velocity_on=(12.0,) * repetitions,
                    velocity_off=(6.0,) * (repetitions - 1),
                )
                self.assertEqual(session_distance(session), Decimal(repetitions))
        self.assertEqual(session_distance(replace(
            self.interval, duration_on=Decimal(30), velocity_on=(12.0, None, None),
        )), Decimal(6))
        self.assertEqual(session_distance(self.endurance), Decimal(0))

    def test_interval_duration_uses_on_duration_times_format_repetitions(self: Self) -> None:
        """Verify continuous threshold and every supported interval effort count."""
        for session_type, repetitions in (
            (SessionType.THRESHOLD, 1), (SessionType.THRESHOLD, 3),
            (SessionType.VO2MAX, 4), (SessionType.VO2MAX, 5), (SessionType.VO2MAX, 6),
        ):
            with self.subTest(session_type=session_type, repetitions=repetitions):
                session = replace(
                    self.interval, session_type=session_type,
                    duration_on=Decimal("5.5"), duration_off=Decimal(10),
                    velocity_on=(12.0,) * repetitions,
                    velocity_off=(6.0,) * (repetitions - 1),
                )
                self.assertEqual(session_duration_seconds(session), Decimal(330 * repetitions))

    def test_endurance_duration_handles_missing_distance_and_unusable_speed(self: Self) -> None:
        """Verify missing measurements and nonpositive speed yield zero effort time."""
        for distance, speed in (
            (None, Decimal(10)), (Decimal(10), None),
            (Decimal(10), Decimal(0)), (Decimal(10), Decimal(-1)),
            (Decimal(0), Decimal(10)),
        ):
            with self.subTest(distance=distance, speed=speed):
                session = replace(self.endurance, distance=distance, velocity=speed)
                self.assertEqual(session_duration_seconds(session), Decimal(0))

    def test_missing_interval_speeds_do_not_remove_effort_repetitions(self: Self) -> None:
        """Verify missing ON speeds reduce distance without reducing format duration."""
        session = replace(
            self.interval, duration_on=Decimal(5),
            velocity_on=(12.0, None, None), velocity_off=(0.0, None),
        )
        self.assertEqual(session_distance(session), Decimal(1))
        self.assertEqual(session_duration_seconds(session), Decimal(900))
        self.assertEqual(session_distance(replace(session, duration_on=None)), Decimal(0))
        self.assertEqual(session_duration_seconds(replace(session, duration_on=None)), Decimal(0))

    def test_fractional_interval_speeds_and_elevation_keep_decimal_precision(self: Self) -> None:
        """Verify fractional speeds and incline estimates introduce no float artifacts."""
        session = replace(
            self.interval, duration_on=Decimal("0.1"),
            velocity_on=(7.1, 8.2, 0.0), inclination=Decimal("5.5"),
        )
        totals = SessionTotals.from_session(session)
        self.assertEqual(totals.distance, Decimal("0.0255"))
        self.assertEqual(totals.elevation_gain, Decimal("1.4025"))
        self.assertEqual(totals.duration_seconds, Decimal(18))

    def test_recorded_elevation_including_zero_precedes_incline_estimate(self: Self) -> None:
        """Verify elevation estimation is used only when recorded elevation is absent."""
        session = replace(self.endurance, distance=Decimal(10), inclination=Decimal(5))
        for elevation, expected in ((None, "500"), (0, "0"), (120, "120")):
            with self.subTest(elevation=elevation):
                totals = SessionTotals.from_session(replace(session, elevation_gain=elevation))
                self.assertEqual(totals.elevation_gain, Decimal(expected))

    def test_aggregation_keeps_empty_families_duplicates_and_independent_weighted_shares(self: Self) -> None:
        """Verify one-pass aggregation retains duplicates and weights cumulative zones."""
        easy = replace(self.endurance, distance=Decimal("2.5"), velocity=Decimal(5),
                       z1=timedelta(minutes=10))
        long_run = replace(self.endurance, distance=Decimal(10), velocity=Decimal(10),
                           z2=timedelta(minutes=80))
        # A single-use iterator ensures aggregation does not depend on replaying input.
        result = summarize_sessions(iter([
            (SessionType.EASY_RUN, easy), (SessionType.LONG_RUN, long_run),
            (SessionType.EASY_RUN, easy),
        ]))
        self.assertEqual(list(result.by_type), [family for family in SessionType if family.has_details])
        self.assertEqual(result.by_type[SessionType.VO2MAX], SessionTotals())
        self.assertEqual(result.by_type[SessionType.EASY_RUN].distance, Decimal(5))
        self.assertEqual(result.by_type[SessionType.EASY_RUN].zone_percentages, (100, 0, 0, 0, 0))
        self.assertEqual(result.overall.distance, Decimal(15))
        self.assertEqual(result.overall.duration_seconds, Decimal(7200))
        self.assertEqual(result.overall.zone_percentages, (20, 80, 0, 0, 0))

    def test_empty_aggregation_has_zero_totals_and_undefined_zone_percentages(self: Self) -> None:
        """Verify empty input retains all running families and undefined zone shares."""
        result = summarize_sessions([])
        self.assertEqual(result.overall, SessionTotals())
        self.assertEqual(result.overall.zone_percentages, (None,) * 5)
        self.assertTrue(all(totals == SessionTotals() for totals in result.by_type.values()))

    def test_totals_and_snapshot_cannot_be_changed_after_aggregation(self: Self) -> None:
        """Verify totals and the family mapping reject mutation at runtime.

        Notes
        -----
        The assignments deliberately violate the read-only type contracts
        to verify their runtime enforcement as well as their annotations.
        """
        result = summarize_sessions([(SessionType.EASY_RUN, self.endurance)])
        with self.assertRaises(FrozenInstanceError):
            result.overall.distance = Decimal(99)  # type: ignore[misc]
        with self.assertRaises(TypeError):
            result.by_type[SessionType.EASY_RUN] = SessionTotals(distance=Decimal(99))  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
