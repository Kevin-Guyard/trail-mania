"""Repository coverage for the inclusive statistics date-range projection."""

import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from typing import Self, cast
from unittest.mock import patch

from sqlalchemy import Connection, Engine, ExecutionContext, event
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania import session_repository
from trail_mania.database import create_database_engine, initialize_database
from trail_mania.models import Session
from trail_mania.session_records import RunningSession
from trail_mania.session_repository import (
    create_session,
    get_detail_fields,
    get_running_sessions_between,
    get_sessions,
)
from trail_mania.session_types import (
    SessionDetailValue,
    SessionDetailValues,
    SessionType,
)


class StatisticsRepositoryTests(unittest.TestCase):
    """Verify immutable running-record projections against isolated SQLite storage.

    Notes
    -----
    Fixtures cover every running family and preserve duplicate dates and
    measurements. SQL execution is observed without replacing the query.
    """

    def setUp(self: Self) -> None:
        """Initialize a temporary database and register engine disposal.

        Notes
        -----
        Cleanup disposes the engine before removing storage and restores the
        application storage environment variable after every test.
        """
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        initialize_database()
        self.engine: Engine = create_database_engine()
        self.addCleanup(self.engine.dispose)

    @staticmethod
    def save(day: date, family: SessionType) -> int:
        """Persist a minimally populated running session for a requested family.

        Parameters
        ----------
        day : datetime.date
            Local calendar date assigned to the parent session.
        family : SessionType
            Running family whose required detail fields should be populated.

        Returns
        -------
        int
            Persistent identity of the created session.

        Notes
        -----
        Required fields use valid values determined by the repository's
        field descriptions. Optional measurements remain absent. Zone times
        exceed one day and interval speeds retain multiple decimal places.
        """
        values: SessionDetailValues = {}
        for name, spec in get_detail_fields(family).items():
            value: SessionDetailValue
            if name == "field_type":
                value = "Route"
            elif name == "slope_type":
                value = "Sans pente"
            elif name == "comment":
                value = "Séance identique"
            elif not spec.required:
                value = None
            elif spec.value_type is timedelta:
                value = timedelta(hours=25)
            elif spec.value_type is Decimal:
                value = Decimal("5.5")
            elif spec.value_type is float:
                value = 12.345
            else:
                value = 150
            values[name] = value
        return create_session(day, family, values)

    def test_all_families_and_duplicates_are_projected_in_one_query_without_calendar_formatting(self: Self) -> None:
        """Verify inclusive projections, stable identities and a single SQL query."""
        start, end = date(2026, 12, 28), date(2027, 1, 3)
        expected: list[tuple[SessionType, RunningSession]] = []
        for family in SessionType:
            if not family.has_details:
                continue
            for day in (start, end, end, start - timedelta(days=1), end + timedelta(days=1)):
                self.save(day, family)
            expected.extend((family, record) for record in get_sessions(family) if start <= record.date <= end)
        expected.sort(key=lambda entry: (entry[1].date, cast(int, entry[1].session_id)))
        create_session(start, SessionType.LEG_STRENGTH)
        with DatabaseSession(self.engine) as db:
            db.add(Session(date=start, session_type=SessionType.EASY_RUN))  # A legacy row with missing details.
            db.commit()
        queries: list[str] = []

        def record_query(
            _connection: Connection,
            _cursor: DBAPICursor,
            statement: str,
            _parameters: object,
            _context: ExecutionContext,
            _executemany: bool,
        ) -> None:
            """Record SQL statements observed by the engine's execution event.

            Parameters
            ----------
            _connection : sqlalchemy.Connection
                Connection about to execute the statement; unused here.
            _cursor : sqlalchemy.engine.interfaces.DBAPICursor
                Driver cursor receiving the statement; unused here.
            statement : str
                SQL statement appended to the observed-query list.
            _parameters : object
                Bound parameters supplied by SQLAlchemy; unused here.
            _context : sqlalchemy.ExecutionContext
                Statement execution context; unused here.
            _executemany : bool
                Whether the driver will execute a parameter batch; unused here.
            """
            queries.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_query)
        with (
            patch.object(session_repository, "create_database_engine", return_value=self.engine),
            patch.object(session_repository, "_calendar_description") as describe,
        ):
            actual = get_running_sessions_between(start, end)
        self.assertEqual(actual, expected)
        self.assertEqual([record.session_id for _, record in actual],
                         [record.session_id for _, record in expected])
        self.assertEqual(len(actual), 15)
        self.assertEqual(len(queries), 1)
        describe.assert_not_called()

    def test_empty_and_strength_only_ranges_return_no_measurements(self: Self) -> None:
        """Verify periods with no running details return no statistics records."""
        day = date(2027, 1, 1)
        self.assertEqual(get_running_sessions_between(day, day), [])
        create_session(day, SessionType.LEG_STRENGTH)
        self.assertEqual(get_running_sessions_between(day, day), [])


if __name__ == "__main__":
    unittest.main()
