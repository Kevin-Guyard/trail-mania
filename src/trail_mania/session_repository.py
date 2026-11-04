"""Read training sessions and persist their optional details atomically."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final, Self, cast

from sqlalchemy import Select, delete, select
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
    RunningSession,
    SessionRecord,
    StrengthSession,
)
from trail_mania.session_types import (
    SESSION_FORMATS,
    SessionDetailValue,
    SessionDetailValues,
    SessionFormat,
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

# Share storage-to-record mappings across queries, calendar hydration and edit
# payloads so each read/write path addresses the same measurements.
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


def _scalar_fields(session_type: SessionType) -> dict[str, str]:
    """Map scalar record attributes to their running-family storage columns.

    Parameters
    ----------
    session_type : SessionType
        Running family whose scalar measurements should be described.

    Returns
    -------
    dict of str to str
        Fresh mapping of common attributes plus ON/OFF durations for interval
        families or distance, speed and heart rates for endurance families.
    """
    return _COMMON_READ_FIELDS | (
        {"duration_on": "duration_ON", "duration_off": "duration_OFF"}
        if session_type.has_format else _ENDURANCE_READ_FIELDS
    )


def _repetition_columns(session_type: SessionType) -> dict[str, tuple[str, ...]]:
    """Map repeated record attributes to their ordered storage columns.

    Parameters
    ----------
    session_type : SessionType
        Family whose maximum repetition count determines the column groups.

    Returns
    -------
    dict of str to tuple of str
        Work-speed, recovery-speed and heart-rate columns in repetition order.
        Recovery has one fewer slot than work. Empty for noninterval families.
    """
    if not session_type.has_format:
        return {}
    repetitions = max(choice.repetitions for choice in SESSION_FORMATS[session_type])
    return {
        attribute: tuple(
            f"{prefix}_{index}"
            for index in range(1, repetitions if attribute == "velocity_off" else repetitions + 1)
        )
        for attribute, prefix in _REPETITION_FIELDS.items()
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
    record : EnduranceSession, IntervalSession, StrengthSession or None, optional
        Immutable measurements for opening supported session details from
        either calendar. None when running details are missing.
    """

    session_type: SessionType
    description: str = ""
    record: SessionRecord | None = None


def get_strength_sessions() -> list[StrengthSession]:
    """Read stored leg-strength dates and their persistent identities.

    Returns
    -------
    list of StrengthSession
        Records ordered by descending date then identity. Equal dates retain
        separate records; an empty database yields an empty list.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If the query or stored-date conversion fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The database must already be initialized. The connection session closes
    and its engine is disposed on every path; no ORM objects escape.
    """
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db:
            return [StrengthSession(day, session_id=session_id) for day, session_id in db.execute(
                select(Session.date, Session.id)
                .where(Session.session_type == SessionType.LEG_STRENGTH)
                .order_by(Session.date.desc(), Session.id.desc())
            )]
    finally:
        engine.dispose()


def get_sessions(session_type: SessionType | str) -> list[RunningSession]:
    """Project one running family into immutable records, newest first.

    Parameters
    ----------
    session_type : SessionType or str
        Running family or its persisted French label.

    Returns
    -------
    list of RunningSession
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
    fields = _scalar_fields(selected_type)
    repetition_fields = _repetition_columns(selected_type)
    query = (
        select(
            Session.date,
            Session.id.label("session_id"),
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
            sessions: list[RunningSession] = []
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


def _sessions_between_query(start: date, end: date) -> Select[tuple[Session]]:
    """Build a date-range query with eagerly loaded running details.

    Parameters
    ----------
    start : datetime.date
        First included calendar date.
    end : datetime.date
        Last included calendar date.

    Returns
    -------
    sqlalchemy.Select
        Session selection ordered by date then identity, with all optional
        one-to-one detail relationships loaded through outer joins.

    Notes
    -----
    Building the query does not open a connection or execute SQL. Calendar
    and statistics readers share it to preserve duplicates and avoid extra
    queries while projecting each session's measurements.
    """
    return (
        select(Session)
        .options(*(
            joinedload(getattr(Session, name))
            for name in _DETAIL_RELATIONSHIPS.values()
        ))
        .where(Session.date.between(start, end))
        .order_by(Session.date, Session.id)
    )


def get_running_sessions_between(start: date, end: date) -> list[tuple[SessionType, RunningSession]]:
    """Read running families and their measurements for an inclusive date range.

    Parameters
    ----------
    start : datetime.date
        First included calendar date.
    end : datetime.date
        Last included calendar date.

    Returns
    -------
    list of (SessionType, RunningSession)
        Running-family and immutable-record pairs ordered by date then
        identity. Duplicate sessions and zero-valued measurements are
        retained. Strength sessions and running sessions without details
        are excluded. No matches yields an empty list.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If the query or stored-value conversion fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The caller initializes storage before reading. One query loads all running
    families without preparing calendar descriptions or grouping records by
    date. The database session closes and its engine is disposed on every
    path; returned records retain no ORM objects.
    """
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db:
            rows = db.scalars(
                _sessions_between_query(start, end)
                .where(Session.session_type != SessionType.LEG_STRENGTH)
            )
            sessions: list[tuple[SessionType, RunningSession]] = []
            for session in rows:
                session_type = SessionType(session.session_type)
                detail = cast(SessionDetailModel | None, getattr(session, _DETAIL_RELATIONSHIPS[session_type]))
                if detail is not None:
                    sessions.append((
                        session_type,
                        _record_from_detail(session_type, detail, session.date, session.id),
                    ))
            return sessions
    finally:
        engine.dispose()


def get_calendar_sessions_by_date(start: date, end: date) -> dict[date, list[CalendarSession]]:
    """Read calendar descriptions and session measurements in one query.

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
            rows = db.scalars(_sessions_between_query(start, end))
            sessions: dict[date, list[CalendarSession]] = {}
            for session in rows:
                session_type = SessionType(session.session_type)
                description = ""
                record: SessionRecord | None = (
                    StrengthSession(session.date, session_id=session.id) if session_type == SessionType.LEG_STRENGTH else None
                )
                if session_type.has_details:
                    detail = getattr(session, _DETAIL_RELATIONSHIPS[session_type])
                    if detail is not None:
                        description = _calendar_description(session_type, detail)
                        record = _record_from_detail(session_type, detail, session.date, session.id)
                sessions.setdefault(session.date, []).append(CalendarSession(session_type, description, record))
            return sessions
    finally:
        engine.dispose()


def _record_from_detail(
    session_type: SessionType, detail: SessionDetailModel, session_date: date, session_id: int,
) -> RunningSession:
    """Project a loaded detail row into an immutable running record.

    Parameters
    ----------
    session_type : SessionType
        Running family identifying the supplied detail model.
    detail : SessionDetailModel
        Loaded ORM detail row with measurements compatible with that family.
    session_date : datetime.date
        Calendar date read from the parent session.
    session_id : int
        Persistent parent identity used by editing and deletion.

    Returns
    -------
    RunningSession
        Endurance or interval record retaining missing values and every
        stored repetition slot, independently of the ORM connection.

    Notes
    -----
    The scalar and repeated-field mappings are shared with list queries.
    This function reads attributes without validating measurements or
    opening another database connection.
    """
    values = {attribute: getattr(detail, column) for attribute, column in _scalar_fields(session_type).items()}
    if session_type.has_format:
        return IntervalSession(
            date=session_date, session_id=session_id, session_type=session_type,
            **values,
            **{attribute: tuple(
                getattr(detail, column) for column in columns
            ) for attribute, columns in _repetition_columns(session_type).items()},
        )
    return EnduranceSession(date=session_date, session_id=session_id, **values)


def _format_from_detail(session_type: SessionType, detail: SessionDetailModel) -> SessionFormat:
    """Infer an interval row's format from its populated speed slots.

    Parameters
    ----------
    session_type : SessionType
        Threshold or VO2max family matching the detail row.
    detail : SessionDetailModel
        Loaded interval measurements exposing the family's speed columns.

    Returns
    -------
    SessionFormat
        Supported format inferred with the same rules as immutable records.
        Zero speeds count as populated slots.

    Notes
    -----
    Callers supply an interval family. The resulting domain value is used
    for both calendar descriptions and edit invariants, avoiding comparisons
    of user-facing description strings.
    """
    columns = _repetition_columns(session_type)
    return session_format_from_speeds(
        session_type,
        tuple(getattr(detail, column) for column in columns["velocity_on"]),
        tuple(getattr(detail, column) for column in columns["velocity_off"]),
    )


def delete_session(session_id: int) -> None:
    """Delete a session by identity together with its cascading detail rows.

    Parameters
    ----------
    session_id : int
        Persistent parent identity to delete; equal measurements or dates do
        not identify other rows for deletion.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If deleting or committing fails. The transaction is rolled back.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    A missing identity is a no-op, allowing an already deleted session to be
    handled idempotently. Foreign-key cascades remove its details in the same
    transaction. The connection closes and the engine is always disposed.
    User confirmation is the caller's responsibility.
    """
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db, db.begin():
            db.execute(delete(Session).where(Session.id == session_id))
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
        session_format = _format_from_detail(session_type, detail)
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


def session_detail_values(record: RunningSession) -> SessionDetailValues:
    """Translate immutable measurements back to storage-field keys.

    Parameters
    ----------
    record : RunningSession
        Endurance or interval measurements to prefill or persist.

    Returns
    -------
    SessionDetailValues
        Fresh dictionary of scalar detail values and individual repetition
        slots. Missing values remain None and zone durations remain timedeltas.
        Parent date and identity are excluded.

    Notes
    -----
    The returned payload includes stored values absent from the visible
    edit form, allowing that form to preserve them during updates.
    No database connection is opened.
    """
    values = {column: getattr(record, attribute) for attribute, column in _COMMON_READ_FIELDS.items()}
    if isinstance(record, EnduranceSession):
        values.update({column: getattr(record, attribute) for attribute, column in _ENDURANCE_READ_FIELDS.items()})
    elif isinstance(record, IntervalSession):
        values.update(duration_ON=record.duration_on, duration_OFF=record.duration_off)
        for attribute, prefix in _REPETITION_FIELDS.items():
            values.update({f"{prefix}_{index}": value for index, value in enumerate(getattr(record, attribute), 1)})
    return values


def update_session(
    session_id: int, session_date: date, session_type: SessionType | str, detail_values: SessionDetailValues | None,
) -> SessionRecord:
    """Update one identity atomically, preserving its family and configuration.

    Parameters
    ----------
    session_id : int
        Persistent identity of the parent session to update.
    session_date : datetime.date
        Replacement calendar date.
    session_type : SessionType or str
        Existing family or its persisted French label; the family cannot change.
    detail_values : SessionDetailValues or None
        Validated detail-column payload for running, including its unchanged
        terrain, slope and movement labels. Must be None for strength sessions.

    Returns
    -------
    SessionRecord
        Detached updated record with the same persistent identity, returned
        only after the transaction commits.

    Raises
    ------
    ValueError
        If the family is unsupported, the session or details are unavailable,
        a field is unknown, or a locked location or interval format changes.
    sqlalchemy.exc.SQLAlchemyError
        If conversion, a database constraint, flushing or committing fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The caller validates measurement contents before submission. Any failure
    rolls back both the date and the measurements. Interval formats are
    inferred from speed-slot occupancy before and after applying the payload.
    The connection closes and its engine is disposed on every path.
    """
    session_type = SessionType(session_type)
    engine = create_database_engine()
    try:
        with DatabaseSession(engine) as db, db.begin():
            session = db.get(Session, session_id)
            if session is None or session.session_type != session_type:
                raise ValueError("La séance n'est plus disponible.")
            session.date = session_date
            record: SessionRecord
            if not session_type.has_details:
                if detail_values is not None:
                    raise ValueError("Muscu jambes has no detail table")
                record = StrengthSession(session_date, session_id=session_id)
            else:
                detail = getattr(session, _DETAIL_RELATIONSHIPS[session_type])
                if detail is None or detail_values is None:
                    raise ValueError("Les mesures de la séance ne sont plus disponibles.")
                for name in ("field_type", "slope_type", "dynamic_type"):
                    if detail_values.get(name) != getattr(detail, name):
                        raise ValueError("Le terrain, la pente et le mouvement ne peuvent pas être modifiés.")
                # The original format must be inferred before its speed slots change.
                previous_format = _format_from_detail(session_type, detail) if session_type.has_format else None
                allowed = get_detail_fields(session_type)
                if detail_values.keys() - allowed.keys():
                    raise ValueError("Unknown session measurements")
                for name, value in detail_values.items():
                    setattr(detail, name, value)
                if session_type.has_format and previous_format != _format_from_detail(session_type, detail):
                    raise ValueError("Le format de la séance ne peut pas être modifié.")
                record = _record_from_detail(session_type, detail, session_date, session_id)
            db.flush()
        return record
    finally:
        engine.dispose()


def create_session(
    session_date: date,
    session_type: SessionType | str,
    detail_values: SessionDetailValues | None = None,
) -> int:
    """Persist a parent session and its optional details in one transaction.

    Parameters
    ----------
    session_date : datetime.date
        Local calendar date assigned to the parent row.
    session_type : SessionType or str
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
