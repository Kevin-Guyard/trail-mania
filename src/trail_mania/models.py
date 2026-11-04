"""SQLAlchemy models for training sessions."""

from datetime import date as DateValue
from datetime import timedelta
from decimal import Decimal
from typing import ClassVar, Self

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)
from sqlalchemy.types import TypeDecorator

from trail_mania.session_types import Movement, SessionType, Slope, Terrain, Weather


class Base(DeclarativeBase):
    """Provide the shared SQLAlchemy declarative registry and metadata.

    Notes
    -----
    All parent and detail models inherit this base. Database initialization
    uses its metadata to create and migrate the independent tables.
    """

    pass


class DurationSeconds(TypeDecorator[timedelta]):
    """Store nonnegative, whole-second timedeltas as SQLite integers.

    Notes
    -----
    The integer representation preserves durations beyond 24 hours.
    None passes through unchanged; column nullability determines whether
    it is permitted. Subsecond and negative durations are rejected.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self: Self, value: timedelta | None, dialect: Dialect) -> int | None:
        """Validate a duration and convert it to integer seconds for storage.

        Parameters
        ----------
        value : datetime.timedelta or None
            Python duration supplied by the ORM.
        dialect : sqlalchemy.engine.Dialect
            Active SQLAlchemy dialect; conversion is dialect-independent.

        Returns
        -------
        int or None
            Nonnegative whole seconds, or None when the input is None.

        Raises
        ------
        TypeError
            If a non-None runtime value is not a timedelta.
        ValueError
            If the duration is negative or includes microseconds.
        """
        if value is None:
            return None
        if not isinstance(value, timedelta):
            raise TypeError("A zone duration must be a datetime.timedelta")
        if value < timedelta(0) or value.microseconds:
            raise ValueError("A zone duration must contain nonnegative whole seconds")
        # Integer arithmetic avoids the precision loss of total_seconds().
        return value.days * 86400 + value.seconds

    def process_result_value(self: Self, value: int | None, dialect: Dialect) -> timedelta | None:
        """Restore an integer second count as a Python timedelta.

        Parameters
        ----------
        value : int or None
            Stored duration supplied by the database driver.
        dialect : sqlalchemy.engine.Dialect
            Active SQLAlchemy dialect; conversion is dialect-independent.

        Returns
        -------
        datetime.timedelta or None
            Duration represented by the stored seconds, preserving None.
        """
        return timedelta(seconds=value) if value is not None else None


class Session(Base):
    """Represent the dated parent row of every training session.

    Attributes
    ----------
    id : int
        Database-generated primary key.
    date : datetime.date
        Local calendar date of the training session.
    session_type : str
        French session-family label constrained by SessionType.
    sortie_longue : SessionSortieLongue or None
        One-to-one long-run details, when present.
    endurance_fondamentale : SessionEnduranceFondamentale or None
        One-to-one easy-endurance details, when present.
    endurance_active : SessionEnduranceActive or None
        One-to-one steady-endurance details, when present.
    seuil : SessionSeuil or None
        One-to-one threshold details, when present.
    vo2max : SessionVO2max or None
        One-to-one VO2max details, when present.

    Notes
    -----
    Strength sessions have no detail row. Deleting a parent cascades
    to its details, whether deletion is performed by the ORM or SQLite.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[DateValue] = mapped_column(Date)
    session_type: Mapped[str] = mapped_column(
        Enum(
            *(session_type.value for session_type in SessionType),
            name="session_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )

    sortie_longue: Mapped["SessionSortieLongue | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    endurance_fondamentale: Mapped["SessionEnduranceFondamentale | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    endurance_active: Mapped["SessionEnduranceActive | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    seuil: Mapped["SessionSeuil | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    vo2max: Mapped["SessionVO2max | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SessionDetailFields:
    """Share location, conditions and exertion columns across detail tables.

    Attributes
    ----------
    id : int
        Detail-row primary key.
    session_id : int
        Required unique foreign key to the parent Session.
    field_type, slope_type : str
        Required French terrain and slope labels.
    dynamic_type : str or None
        Optional French walking or running label.
    elevation_gain, temperature : int or None
        Optional outdoor elevation in meters and temperature in degrees Celsius.
    inclination : decimal.Decimal or None
        Optional signed treadmill inclination in percent, with one decimal place.
    weather : str or None
        Optional canonical French weather label.
    Z1, Z2, Z3, Z4, Z5 : datetime.timedelta
        Required nonnegative, whole-second zone durations.
    RPE : decimal.Decimal
        Required perceived exertion with one decimal place.
    comment : str
        Required comment text; an empty string is allowed.

    Notes
    -----
    Each concrete detail table owns independent rows and constraints.
    SQLite checks supplement type affinity to enforce decimal precision,
    integer fields and valid duration storage.
    """

    _decimal_fields: ClassVar[tuple[str, ...]] = ("inclination", "RPE")
    _integer_fields: ClassVar[tuple[str, ...]] = ("elevation_gain", "temperature")

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
    )
    field_type: Mapped[str] = mapped_column(
        Enum(
            *(terrain.label for terrain in Terrain),
            name="field_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )
    slope_type: Mapped[str] = mapped_column(
        Enum(
            *(slope.label for slope in Slope),
            name="slope_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )
    dynamic_type: Mapped[str | None] = mapped_column(
        Enum(
            *(movement.label for movement in Movement),
            name="dynamic_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )
    elevation_gain: Mapped[int | None] = mapped_column(Integer)
    inclination: Mapped[Decimal | None] = mapped_column(Numeric(scale=1))
    temperature: Mapped[int | None] = mapped_column(Integer)
    weather: Mapped[str | None] = mapped_column(
        Enum(
            *(weather.label for weather in Weather),
            name="weather",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )
    Z1: Mapped[timedelta] = mapped_column(DurationSeconds())
    Z2: Mapped[timedelta] = mapped_column(DurationSeconds())
    Z3: Mapped[timedelta] = mapped_column(DurationSeconds())
    Z4: Mapped[timedelta] = mapped_column(DurationSeconds())
    Z5: Mapped[timedelta] = mapped_column(DurationSeconds())
    RPE: Mapped[Decimal] = mapped_column(Numeric(scale=1))
    comment: Mapped[str] = mapped_column(Text)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls: type[Self]) -> tuple[CheckConstraint, ...]:
        """Build precision, integer-storage and duration checks for a detail table.

        Returns
        -------
        tuple of sqlalchemy.CheckConstraint
            Fresh checks incorporating the concrete subclass's numeric field lists.

        Notes
        -----
        SQLAlchemy evaluates this declared attribute for each concrete table.
        Fresh constraint objects avoid sharing table-bound constraints between
        models; subclass field lists extend the shared validation rules.
        """
        # SQLite type affinity alone does not enforce scale or whole integers.
        decimals = tuple(
            CheckConstraint(
                f'"{name}" = round("{name}", 1)',
                name=f"{name}_one_decimal",
            )
            for name in cls._decimal_fields
        )
        integers = tuple(
            CheckConstraint(
                f'"{name}" IS NULL OR typeof("{name}") = \'integer\'',
                name=f"{name}_integer",
            )
            for name in cls._integer_fields
        )
        durations = tuple(
            CheckConstraint(
                f'typeof("{name}") = \'integer\' AND "{name}" >= 0',
                name=f"{name}_duration_seconds",
            )
            for name in ("Z1", "Z2", "Z3", "Z4", "Z5")
        )
        return decimals + integers + durations


class RunningSessionFields(SessionDetailFields):
    """Share distance-based measurements across the three endurance families.

    Attributes
    ----------
    distance : decimal.Decimal
        Required distance in kilometers, with one decimal place.
    velocity : decimal.Decimal
        Required speed in km/h, with one decimal place.
    mean_HR, max_HR : int
        Required average and maximum heart rates in beats per minute.
    """

    _decimal_fields: ClassVar[tuple[str, ...]] = SessionDetailFields._decimal_fields + (
        "distance",
        "velocity",
    )
    _integer_fields: ClassVar[tuple[str, ...]] = SessionDetailFields._integer_fields + (
        "mean_HR",
        "max_HR",
    )

    distance: Mapped[Decimal] = mapped_column(Numeric(scale=1))
    velocity: Mapped[Decimal] = mapped_column(Numeric(scale=1))
    mean_HR: Mapped[int] = mapped_column(Integer)
    max_HR: Mapped[int] = mapped_column(Integer)


class IntervalSessionFields(SessionDetailFields):
    """Share effort and recovery timing across threshold and VO2max tables.

    Attributes
    ----------
    duration_ON : decimal.Decimal
        Required work duration in minutes, with one decimal place.
    duration_OFF : decimal.Decimal or None
        Optional recovery duration in minutes, with one decimal place.

    Notes
    -----
    These values are minute quantities, unlike the timedelta values
    used by the inherited heart-rate-zone columns.
    """

    _decimal_fields: ClassVar[tuple[str, ...]] = SessionDetailFields._decimal_fields + (
        "duration_ON",
        "duration_OFF",
    )

    duration_ON: Mapped[Decimal] = mapped_column(Numeric(scale=1))
    duration_OFF: Mapped[Decimal | None] = mapped_column(Numeric(scale=1))


class SessionSortieLongue(RunningSessionFields, Base):
    """Store the distance-based details of a long-run session.

    Attributes
    ----------
    session : Session
        Parent session, paired with Session.sortie_longue.

    Notes
    -----
    Inherits location, weather, heart-rate zones and exertion fields from
    SessionDetailFields, plus distance, speed and heart rates from
    RunningSessionFields. The parent foreign key is required and unique.
    """

    __tablename__ = "sessions_sortie_longue"

    session: Mapped[Session] = relationship(back_populates="sortie_longue")


class SessionEnduranceFondamentale(RunningSessionFields, Base):
    """Store the distance-based details of a easy-endurance session.

    Attributes
    ----------
    session : Session
        Parent session, paired with Session.endurance_fondamentale.

    Notes
    -----
    Inherits location, weather, heart-rate zones and exertion fields from
    SessionDetailFields, plus distance, speed and heart rates from
    RunningSessionFields. The parent foreign key is required and unique.
    """

    __tablename__ = "sessions_endurance_fondamentale"

    session: Mapped[Session] = relationship(back_populates="endurance_fondamentale")


class SessionEnduranceActive(RunningSessionFields, Base):
    """Store the distance-based details of a steady-endurance session.

    Attributes
    ----------
    session : Session
        Parent session, paired with Session.endurance_active.

    Notes
    -----
    Inherits location, weather, heart-rate zones and exertion fields from
    SessionDetailFields, plus distance, speed and heart rates from
    RunningSessionFields. The parent foreign key is required and unique.
    """

    __tablename__ = "sessions_endurance_active"

    session: Mapped[Session] = relationship(back_populates="endurance_active")


class SessionSeuil(IntervalSessionFields, Base):
    """Store a continuous threshold effort or up to three work repetitions.

    Attributes
    ----------
    session : Session
        Parent session, paired with Session.seuil.
    velocity_ON_1 : float
        Required speed of the first work interval, in km/h.
    velocity_ON_2, velocity_ON_3 : float or None
        Optional speeds of the second and third work intervals, in km/h.
    velocity_OFF_1, velocity_OFF_2 : float or None
        Optional recovery speeds between work intervals.
    mean_HR_ON_1, max_HR_ON_1 : int
        Required first-effort heart rates in beats per minute.

    Notes
    -----
    Heart rates for repetitions two and three are optional integers.
    Continuous forms populate only the first work speed and heart-rate
    pair. Unused recovery and repetition columns remain NULL.
    """

    __tablename__ = "sessions_seuil"

    _integer_fields: ClassVar[tuple[str, ...]] = IntervalSessionFields._integer_fields + (
        "mean_HR_ON_1",
        "max_HR_ON_1",
        "mean_HR_ON_2",
        "max_HR_ON_2",
        "mean_HR_ON_3",
        "max_HR_ON_3",
    )

    velocity_ON_1: Mapped[float] = mapped_column(Float)
    velocity_OFF_1: Mapped[float | None] = mapped_column(Float)
    velocity_ON_2: Mapped[float | None] = mapped_column(Float)
    velocity_OFF_2: Mapped[float | None] = mapped_column(Float)
    velocity_ON_3: Mapped[float | None] = mapped_column(Float)
    mean_HR_ON_1: Mapped[int] = mapped_column(Integer)
    max_HR_ON_1: Mapped[int] = mapped_column(Integer)
    mean_HR_ON_2: Mapped[int | None] = mapped_column(Integer)
    max_HR_ON_2: Mapped[int | None] = mapped_column(Integer)
    mean_HR_ON_3: Mapped[int | None] = mapped_column(Integer)
    max_HR_ON_3: Mapped[int | None] = mapped_column(Integer)

    session: Mapped[Session] = relationship(back_populates="seuil")


class SessionVO2max(IntervalSessionFields, Base):
    """Store a VO2max session containing four, five or six work repetitions.

    Attributes
    ----------
    session : Session
        Parent session, paired with Session.vo2max.
    velocity_ON_1, velocity_ON_2, velocity_ON_3, velocity_ON_4 : float
        Required speeds for the first four work intervals, in km/h.
    velocity_OFF_1, velocity_OFF_2, velocity_OFF_3 : float
        Required speeds for the first three recoveries, in km/h.

    Notes
    -----
    The first four work intervals require integer average and maximum
    heart rates. Fifth and sixth work speeds and heart rates, plus fourth
    and fifth recovery speeds, are optional. Forms leave repetitions
    beyond the chosen count and the final recovery as NULL.
    """

    __tablename__ = "sessions_vo2max"

    _integer_fields: ClassVar[tuple[str, ...]] = IntervalSessionFields._integer_fields + (
        "mean_HR_ON_1",
        "max_HR_ON_1",
        "mean_HR_ON_2",
        "max_HR_ON_2",
        "mean_HR_ON_3",
        "max_HR_ON_3",
        "mean_HR_ON_4",
        "max_HR_ON_4",
        "mean_HR_ON_5",
        "max_HR_ON_5",
        "mean_HR_ON_6",
        "max_HR_ON_6",
    )

    velocity_ON_1: Mapped[float] = mapped_column(Float)
    velocity_OFF_1: Mapped[float] = mapped_column(Float)
    velocity_ON_2: Mapped[float] = mapped_column(Float)
    velocity_OFF_2: Mapped[float] = mapped_column(Float)
    velocity_ON_3: Mapped[float] = mapped_column(Float)
    velocity_OFF_3: Mapped[float] = mapped_column(Float)
    velocity_ON_4: Mapped[float] = mapped_column(Float)
    velocity_OFF_4: Mapped[float | None] = mapped_column(Float)
    velocity_ON_5: Mapped[float | None] = mapped_column(Float)
    velocity_OFF_5: Mapped[float | None] = mapped_column(Float)
    velocity_ON_6: Mapped[float | None] = mapped_column(Float)
    mean_HR_ON_1: Mapped[int] = mapped_column(Integer)
    max_HR_ON_1: Mapped[int] = mapped_column(Integer)
    mean_HR_ON_2: Mapped[int] = mapped_column(Integer)
    max_HR_ON_2: Mapped[int] = mapped_column(Integer)
    mean_HR_ON_3: Mapped[int] = mapped_column(Integer)
    max_HR_ON_3: Mapped[int] = mapped_column(Integer)
    mean_HR_ON_4: Mapped[int] = mapped_column(Integer)
    max_HR_ON_4: Mapped[int] = mapped_column(Integer)
    mean_HR_ON_5: Mapped[int | None] = mapped_column(Integer)
    max_HR_ON_5: Mapped[int | None] = mapped_column(Integer)
    mean_HR_ON_6: Mapped[int | None] = mapped_column(Integer)
    max_HR_ON_6: Mapped[int | None] = mapped_column(Integer)

    session: Mapped[Session] = relationship(back_populates="vo2max")
