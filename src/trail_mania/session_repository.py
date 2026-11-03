"""Persist a training session and its optional details atomically."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final, Self, cast

from sqlalchemy.orm import Session as DatabaseSession

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
from trail_mania.session_types import (
    SessionDetailValue,
    SessionDetailValues,
    SessionInputValue,
    SessionType,
)

type SessionDetailModel = (
    SessionSortieLongue
    | SessionEnduranceFondamentale
    | SessionEnduranceActive
    | SessionSeuil
    | SessionVO2max
)
type DetailValueType = type[Decimal] | type[float] | type[int] | type[str] | type[timedelta]


DETAIL_MODELS: Final[dict[SessionType, type[SessionDetailModel]]] = {
    SessionType.LONG_RUN: SessionSortieLongue,
    SessionType.EASY_RUN: SessionEnduranceFondamentale,
    SessionType.STEADY_RUN: SessionEnduranceActive,
    SessionType.THRESHOLD: SessionSeuil,
    SessionType.VO2MAX: SessionVO2max,
}


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
        with DatabaseSession(engine) as db:
            with db.begin():
                session = Session(date=session_date, session_type=selected_type)
                db.add(session)
                if model is not None and detail_values is not None:
                    db.add(model(session=session, **detail_values))
                db.flush()
                session_id = session.id
        return session_id
    finally:
        engine.dispose()
