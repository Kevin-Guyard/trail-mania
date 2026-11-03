"""Read training sessions and persist their optional details atomically."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final, Self, cast

from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession
from sqlalchemy.orm import joinedload

from trail_mania.database import create_database_engine
from trail_mania.models import (
    DurationSeconds,
    Session,
    SessionEnduranceActive,
    SessionEnduranceFondamentale,
    SessionSeuil,
    SessionSortieLongue,
    SessionVO2max,
)
from trail_mania.session_records import (
    EnduranceSession,
    IntervalSession,
    RecordedSession,
)
from trail_mania.session_types import (
    SESSION_FORMATS,
    SessionDetailValue,
    SessionDetailValues,
    SessionInputValue,
    SessionType,
    Slope,
    Terrain,
    session_format_from_speeds,
)

type SessionDetailModel = (
    SessionSortieLongue
    | SessionEnduranceFondamentale
    | SessionEnduranceActive
    | SessionSeuil
    | SessionVO2max
)
type DetailValueType = type[Decimal | float | int | str | timedelta]


DETAIL_MODELS: Final[dict[SessionType, type[SessionDetailModel]]] = {
    SessionType.LONG_RUN: SessionSortieLongue,
    SessionType.EASY_RUN: SessionEnduranceFondamentale,
    SessionType.STEADY_RUN: SessionEnduranceActive,
    SessionType.THRESHOLD: SessionSeuil,
    SessionType.VO2MAX: SessionVO2max,
}

_DETAIL_RELATIONSHIPS: Final[dict[SessionType, str]] = {
    SessionType.LONG_RUN: "sortie_longue",
    SessionType.EASY_RUN: "endurance_fondamentale",
    SessionType.STEADY_RUN: "endurance_active",
    SessionType.THRESHOLD: "seuil",
    SessionType.VO2MAX: "vo2max",
}

# Query aliases translate storage names into record constructor arguments.
# This mapping keeps SQL column names out of the view and record definitions.
_COMMON_READ_FIELDS: Final[dict[str, str]] = {
    "terrain": "field_type",
    "slope": "slope_type",
    "movement": "dynamic_type",
    "inclination": "inclination",
    "elevation_gain": "elevation_gain",
    "temperature": "temperature",
    "weather": "weather",
    **{f"z{index}": f"Z{index}" for index in range(1, 6)},
    "rpe": "RPE",
    "comment": "comment",
}
_ENDURANCE_READ_FIELDS: Final[dict[str, str]] = {
    "distance": "distance",
    "velocity": "velocity",
    "mean_hr": "mean_HR",
    "max_hr": "max_HR",
}
_REPETITION_FIELDS: Final[dict[str, str]] = {
    "velocity_on": "velocity_ON",
    "velocity_off": "velocity_OFF",
    "mean_hr_on": "mean_HR_ON",
    "max_hr_on": "max_HR_ON",
}


@dataclass(frozen=True)
class CalendarSession:
    """Store a session's palette key and weekly calendar description.

    Parameters
    ----------
    session_type : SessionType
        Family used to choose the calendar band's color.
    description : str, optional
        Formatted location and interval description. Defaults to an empty
        string, also used for strength sessions or missing detail rows.
    """

    session_type: SessionType
    description: str = ""


def get_sessions(session_type: SessionType | str) -> list[RecordedSession]:
    """Project one running family into immutable records, newest first.

    Parameters
    ----------
    session_type : SessionType or str
        Running family or its persisted French label.

    Returns
    -------
    list of RecordedSession
        EnduranceSession or IntervalSession records, ordered by descending
        date then ID. Duplicate sessions are retained; no matches yields an
        empty list. Missing measurements remain None.

    Raises
    ------
    ValueError
        If the type is unknown or has no running measurements.
    sqlalchemy.exc.SQLAlchemyError
        If the query or stored-value conversion fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The caller initializes the database before reading, as at app startup.
    One query reads only measurements without constructing ORM objects. The
    connection session closes and its engine is disposed before returning,
    including when reading or record construction fails.
    """
    selected_type = SessionType(session_type)
    if not selected_type.has_details:
        raise ValueError("A running session type is required")
    model = DETAIL_MODELS[selected_type]
    fields = dict(_COMMON_READ_FIELDS)
    repetition_fields: dict[str, tuple[str, ...]] = {}
    if selected_type.has_format:
        fields.update(duration_on="duration_ON", duration_off="duration_OFF")
        repetitions = max(choice.repetitions for choice in SESSION_FORMATS[selected_type])
        repetition_fields = {
            attribute: tuple(
                f"{prefix}_{index}"
                for index in range(1, repetitions + 1)
                if attribute != "velocity_off" or index < repetitions
            )
            for attribute, prefix in _REPETITION_FIELDS.items()
        }
    else:
        fields.update(_ENDURANCE_READ_FIELDS)
    query = (
        select(
            Session.date,
            *(getattr(model, column).label(attribute) for attribute, column in fields.items()),
            *(getattr(model, column) for columns in repetition_fields.values() for column in columns),
        )
        .join(model, model.session_id == Session.id)
        .where(Session.session_type == selected_type)
        .order_by(Session.date.desc(), Session.id.desc())
    )
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db:
            sessions: list[RecordedSession] = []
            for row in db.execute(query).mappings():
                values = dict(row)
                if selected_type.has_format:
                    # Remove individual SQL columns before unpacking the common
                    # measurements; each repetition group becomes one tuple.
                    repeated_values = {
                        attribute: tuple(values.pop(column) for column in columns)
                        for attribute, columns in repetition_fields.items()
                    }
                    sessions.append(IntervalSession(
                        session_type=selected_type, **values, **repeated_values,
                    ))
                else:
                    sessions.append(EnduranceSession(**values))
            return sessions
    finally:
        engine.dispose()


def get_calendar_sessions_by_date(start: date, end: date) -> dict[date, list[CalendarSession]]:
    """Read weekly session descriptions with details loaded in a single query.

    Parameters
    ----------
    start : datetime.date
        First included calendar date.
    end : datetime.date
        Last included calendar date.

    Returns
    -------
    dict of datetime.date to list of CalendarSession
        Dates with recorded sessions, in chronological order. Each day's list
        preserves insertion order and duplicates. Dates without sessions are
        omitted; descriptions are empty for strength or absent detail rows.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If the query or stored-value conversion fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The caller initializes the database before reading. Details are eagerly
    loaded, and formats use the same speed-slot inference as the session list.
    The connection session closes and its engine is disposed on every path.
    """
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db:
            rows = db.scalars(
                select(Session)
                .options(*(
                    joinedload(getattr(Session, name))
                    for name in _DETAIL_RELATIONSHIPS.values()
                ))
                .where(Session.date.between(start, end))
                .order_by(Session.date, Session.id)
            )
            sessions: dict[date, list[CalendarSession]] = {}
            for session in rows:
                session_type = SessionType(session.session_type)
                description = ""
                if session_type.has_details:
                    detail = getattr(session, _DETAIL_RELATIONSHIPS[session_type])
                    if detail is not None:
                        description = _calendar_description(session_type, detail)
                sessions.setdefault(session.date, []).append(CalendarSession(session_type, description))
            return sessions
    finally:
        engine.dispose()


def _calendar_description(session_type: SessionType, detail: SessionDetailModel) -> str:
    """Format a detail row as a weekly calendar description.

    Parameters
    ----------
    session_type : SessionType
        Running family corresponding to the supplied detail model.
    detail : SessionDetailModel
        Loaded detail row containing canonical labels and measurements.

    Returns
    -------
    str
        Terrain and slope labels, movement for inclined treadmills when
        present, and ``xN`` for interval formats, joined with `` - ``.

    Notes
    -----
    Continuous threshold efforts display ``x1``. Partially populated optional
    repetitions use the same format inference as IntervalSession records.
    """
    parts = [detail.field_type, detail.slope_type]
    if (
        detail.field_type == Terrain.TREADMILL.label
        and detail.slope_type == Slope.HILLY.label
        and detail.dynamic_type
    ):
        parts.append(detail.dynamic_type)
    if session_type.has_format:
        repetitions = max(choice.repetitions for choice in SESSION_FORMATS[session_type])
        session_format = session_format_from_speeds(
            session_type,
            tuple(getattr(detail, f"velocity_ON_{i}") for i in range(1, repetitions + 1)),
            tuple(getattr(detail, f"velocity_OFF_{i}") for i in range(1, repetitions)),
        )
        parts.append(f"x{session_format.repetitions or 1}")
    return " - ".join(parts)


def get_session_types_by_date(start: date, end: date) -> dict[date, list[SessionType]]:
    """Read session types in an inclusive date range, ordered by insertion ID.

    Parameters
    ----------
    start : datetime.date
        First included calendar date.
    end : datetime.date
        Last included calendar date.

    Returns
    -------
    dict of datetime.date to list of SessionType
        Dates in chronological order, each containing its session types in
        insertion order. Repeated types are retained for separate calendar
        bands. Dates without sessions are omitted.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If reading session dates or types fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The caller initializes the database before reading. No detail models are
    loaded. The connection session closes and its engine is disposed on every
    path.
    """
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db:
            rows = db.execute(
                select(Session.date, Session.session_type)
                .where(Session.date.between(start, end))
                .order_by(Session.date, Session.id)
            )
            sessions: dict[date, list[SessionType]] = {}
            for day, session_type in rows:
                sessions.setdefault(day, []).append(SessionType(session_type))
            return sessions
    finally:
        engine.dispose()


@dataclass(frozen=True)
class DetailField:
    """Expose a detail column's requirements without exposing ORM objects.

    Parameters
    ----------
    required : bool
        Whether the underlying database column disallows NULL.
    value_type : DetailValueType
        Target Python type: Decimal, float, int, str or timedelta.

    Notes
    -----
    Instances are derived from the model schema, keeping form validation
    and value conversion aligned with the persistence requirements.
    """

    required: bool
    value_type: DetailValueType

    def convert(self: Self, value: SessionInputValue) -> SessionDetailValue:
        """Convert a validated input to the column's expected Python value.

        Parameters
        ----------
        value : SessionInputValue
            Normalized input value; duration fields supply integer seconds.

        Returns
        -------
        SessionDetailValue
            Converted scalar or timedelta, preserving None for an empty input.

        Raises
        ------
        ValueError
            If a nonempty value cannot be converted to the target numeric type.
        decimal.InvalidOperation
            If Decimal conversion fails.
        OverflowError
            If the duration exceeds timedelta's supported range.

        Notes
        -----
        Requiredness and input-format validation are handled by the form
        before conversion. Interval speeds use float; scaled measurements
        use Decimal; zones use timedelta rather than minute values.
        """
        if value is None:
            return None
        if self.value_type is Decimal:
            return Decimal(value)
        if self.value_type is float:
            return float(value)
        if self.value_type is int:
            return int(value)
        if self.value_type is str:
            return str(value)
        # ZoneDurationInput supplies whole seconds for duration columns.
        return timedelta(seconds=cast(int, value))


def get_detail_fields(session_type: SessionType) -> dict[str, DetailField]:
    """Describe editable columns using model types and nullability.

    Parameters
    ----------
    session_type : SessionType
        Running session type identifying a detail model.

    Returns
    -------
    dict of str to DetailField
        Column requirements keyed by name, excluding generated IDs and foreign keys.

    Raises
    ------
    KeyError
        If the session type has no registered detail table, including leg strength.

    Notes
    -----
    Reads model metadata only and does not open a database connection.
    DurationSeconds columns are exposed as timedelta targets explicitly.
    """
    return {
        column.name: DetailField(
            required=not column.nullable,
            value_type=(
                timedelta if isinstance(column.type, DurationSeconds) else column.type.python_type
            ),
        )
        for column in DETAIL_MODELS[session_type].__table__.c
        if column.name not in ("id", "session_id")
    }


def create_session(
    session_date: date,
    session_type: str,
    detail_values: SessionDetailValues | None = None,
) -> int:
    """Persist a parent session and its optional details in one transaction.

    Parameters
    ----------
    session_date : datetime.date
        Local calendar date assigned to the parent row.
    session_type : str
        SessionType member or its supported French string value.
    detail_values : SessionDetailValues or None, optional
        Converted detail-column values; required for running and absent for strength.

    Returns
    -------
    int
        Identifier of the committed parent session.

    Raises
    ------
    ValueError
        If the type is unsupported or detail presence does not match the type.
    sqlalchemy.exc.SQLAlchemyError
        If storage access, conversion or a database constraint fails.
    OSError
        If the database's storage directory cannot be created or accessed.

    Notes
    -----
    Failure to insert either row rolls back the entire transaction. The
    database session closes and its engine is disposed on every path.
    Callers validate field contents before invoking this function.
    """
    selected_type = SessionType(session_type)
    model: type[SessionDetailModel] | None
    if not selected_type.has_details:
        if detail_values is not None:
            raise ValueError("Muscu jambes has no detail table")
        model = None
    else:
        model = DETAIL_MODELS[selected_type]
        if detail_values is None:
            raise ValueError("Session details are required")

    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db, db.begin():
            session = Session(date=session_date, session_type=selected_type)
            db.add(session)
            if model is not None and detail_values is not None:
                db.add(model(session=session, **detail_values))
            db.flush()
            session_id = session.id
        return session_id
    finally:
        engine.dispose()
