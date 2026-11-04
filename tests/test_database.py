import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import CheckConstraint, Integer, MetaData, Numeric, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.database import create_database_engine, get_database_path, initialize_database
from trail_mania.session_repository import get_session_types_by_date
from trail_mania.session_types import SessionType
from trail_mania.models import (
    Session,
    SessionEnduranceActive,
    SessionEnduranceFondamentale,
    SessionSortieLongue,
)


DETAIL_MODELS = (
    (SessionSortieLongue, "Sortie longue", "sortie_longue"),
    (SessionEnduranceFondamentale, "Endurance fondamentale", "endurance_fondamentale"),
    (SessionEnduranceActive, "Endurance active", "endurance_active"),
)


def detail_values():
    return dict(
        field_type="Terrain technique", slope_type="Avec pente", dynamic_type=None,
        distance=Decimal("21.3"), velocity=Decimal("9.5"),
        elevation_gain=None, inclination=None, temperature=None, weather="Vent & pluie",
        mean_HR=145, max_HR=178,
        Z1=timedelta(hours=1, minutes=2, seconds=3),
        Z2=timedelta(minutes=45), Z3=timedelta(minutes=10),
        Z4=timedelta(seconds=30), Z5=timedelta(0),
        RPE=Decimal("6.5"), comment="Montée agréable\nÀ refaire !",
    )


class DatabaseTests(unittest.TestCase):
    def test_calendar_session_query_preserves_duplicates_and_inclusive_range(self):
        first, last = date(2026, 12, 31), date(2027, 1, 1)
        with DatabaseSession(self.engine) as db:
            db.add_all([
                Session(date=first - timedelta(days=1), session_type=SessionType.VO2MAX),
                Session(date=first, session_type=SessionType.EASY_RUN),
                Session(date=first, session_type=SessionType.LEG_STRENGTH),
                Session(date=last, session_type=SessionType.THRESHOLD),
                Session(date=last, session_type=SessionType.THRESHOLD),
                Session(date=last + timedelta(days=1), session_type=SessionType.LONG_RUN),
            ])
            db.commit()
        self.assertEqual(get_session_types_by_date(first, last), {
            first: [SessionType.EASY_RUN, SessionType.LEG_STRENGTH],
            last: [SessionType.THRESHOLD, SessionType.THRESHOLD],
        })
        self.assertEqual(get_session_types_by_date(date(2025, 1, 1), date(2025, 1, 2)), {})

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        storage = Path(directory.name) / "persistent data"
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": str(storage)}))
        initialize_database()
        self.engine = create_database_engine()
        self.addCleanup(self.engine.dispose)

    def save_detail(self, model, session_type):
        with DatabaseSession(self.engine) as db:
            parent = Session(date=date(2026, 11, 3), session_type=session_type)
            detail = model(session=parent, **detail_values())
            db.add(detail)
            db.commit()
            return detail.id, parent.id

    def test_schema_and_nullable_columns(self):
        inspector = inspect(self.engine)
        self.assertEqual(set(inspector.get_table_names()), {
            "sessions", "sessions_seuil", "sessions_vo2max",
            *(model.__tablename__ for model, _, _ in DETAIL_MODELS),
        })
        self.assertEqual(
            {column["name"] for column in inspector.get_columns("sessions")},
            {"id", "date", "session_type"},
        )
        expected_columns = {"id", "session_id", *detail_values()}
        for model, _, _ in DETAIL_MODELS:
            with self.subTest(table=model.__tablename__):
                columns = inspector.get_columns(model.__tablename__)
                self.assertEqual({column["name"] for column in columns}, expected_columns)
                self.assertEqual(
                    {column["name"] for column in columns if column["nullable"]},
                    {"dynamic_type", "elevation_gain", "inclination", "temperature", "weather"},
                )
                with self.engine.connect() as connection:
                    self.assertEqual(connection.scalar(select(model.id)), None)

    def test_round_trip_and_relationships_for_all_detail_tables(self):
        for model, session_type, relation in DETAIL_MODELS:
            with self.subTest(model=model):
                detail_id, parent_id = self.save_detail(model, session_type)
                with DatabaseSession(self.engine) as db:
                    detail = db.get(model, detail_id)
                    parent = db.get(Session, parent_id)
                    self.assertIs(detail.session, parent)
                    self.assertIs(getattr(parent, relation), detail)
                    self.assertEqual(parent.date, date(2026, 11, 3))
                    self.assertEqual(parent.session_type, session_type)
                    for field, expected in detail_values().items():
                        self.assertEqual(getattr(detail, field), expected)
                    self.assertIsInstance(detail.distance, Decimal)

    def test_all_six_session_types_are_accepted(self):
        types = (
            "Muscu jambes", "Sortie longue", "Endurance fondamentale",
            "Endurance active", "Seuil", "VO2max",
        )
        with DatabaseSession(self.engine) as db:
            db.add_all(Session(date=date(2026, 11, 3), session_type=value) for value in types)
            db.commit()
            self.assertEqual(set(db.scalars(select(Session.session_type))), set(types))

    def test_each_allowed_detail_choice(self):
        choices = {
            "field_type": ("Route", "Terrain roulant", "Terrain technique", "Tapis"),
            "slope_type": ("Sans pente", "Avec pente"),
            "dynamic_type": ("Marche", "Course", None),
            "weather": ("Normal", "Vent", "Pluie", "Vent & pluie"),
        }
        for model, session_type, _ in DETAIL_MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            for field, values in choices.items():
                for value in values:
                    with self.subTest(model=model, field=field, value=value):
                        with DatabaseSession(self.engine) as db:
                            detail = db.get(model, detail_id)
                            setattr(detail, field, value)
                            db.commit()
                            self.assertEqual(getattr(detail, field), value)

    def test_database_rejects_invalid_choices_and_extra_decimals(self):
        with self.engine.begin() as connection:
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO sessions (date, session_type) VALUES ('2026-11-03', 'Inconnu')"
                )
        invalid = {
            "field_type": "Inconnu", "slope_type": "Inconnu",
            "dynamic_type": "Inconnu", "weather": "Inconnu",
            "distance": 12.34, "velocity": 8.91, "RPE": 6.78,
            "mean_HR": 145.5, "max_HR": 178.5,
            "elevation_gain": 1.5, "inclination": 1.55, "temperature": 1.5,
            "Z1": -1, "Z2": 1.5, "Z3": "01:02:03",
        }
        for model, session_type, _ in DETAIL_MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            for field, value in invalid.items():
                with self.subTest(table=model.__tablename__, field=field):
                    with self.engine.begin() as connection:
                        with self.assertRaises(IntegrityError):
                            connection.execute(text(
                                f'UPDATE {model.__tablename__} SET "{field}" = :value WHERE id = :id'
                            ), {"value": value, "id": detail_id})

    def test_inclination_accepts_one_decimal_or_null_in_all_tables(self):
        for model, session_type, _ in DETAIL_MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            for value in (Decimal("5.5"), Decimal("0.0"), Decimal("-2.5"), None):
                with self.subTest(model=model, value=value):
                    with DatabaseSession(self.engine) as db:
                        detail = db.get(model, detail_id)
                        detail.inclination = value
                        db.commit()
                        self.assertEqual(detail.inclination, value)
                        if value is not None:
                            self.assertIsInstance(detail.inclination, Decimal)

    def test_migrates_old_integer_inclinations_without_losing_data(self):
        # Reproduce the previous schema, including its INTEGER-only constraint.
        metadata = MetaData()
        Session.__table__.to_metadata(metadata)
        for model, _, _ in DETAIL_MODELS:
            legacy = model.__table__.to_metadata(metadata)
            legacy.c.inclination.type = Integer()
            legacy.constraints.remove(next(
                constraint for constraint in legacy.constraints
                if constraint.name == "inclination_one_decimal"
            ))
            legacy.append_constraint(CheckConstraint(
                "inclination IS NULL OR typeof(inclination) = 'integer'",
                name="inclination_integer",
            ))
        metadata.drop_all(self.engine)
        metadata.create_all(self.engine)
        saved = []
        for model, session_type, _ in DETAIL_MODELS:
            for old_value in (5, None):
                detail_id, parent_id = self.save_detail(model, session_type)
                with self.engine.begin() as connection:
                    connection.execute(text(
                        f'UPDATE {model.__tablename__} SET inclination = :value WHERE id = :id'
                    ), {"value": old_value, "id": detail_id})
                saved.append((model, detail_id, parent_id, old_value))

        initialize_database()
        initialize_database()
        for model, detail_id, parent_id, old_value in saved:
            with self.subTest(model=model, old_value=old_value):
                columns = inspect(self.engine).get_columns(model.__tablename__)
                self.assertIsInstance(next(
                    column["type"] for column in columns if column["name"] == "inclination"
                ), Numeric)
                with DatabaseSession(self.engine) as db:
                    detail = db.get(model, detail_id)
                    self.assertEqual(detail.inclination, old_value)
                    self.assertEqual(detail.session.id, parent_id)
                    for field, expected in detail_values().items():
                        if field != "inclination":
                            self.assertEqual(getattr(detail, field), expected)
                    detail.inclination = Decimal("5.5")
                    db.commit()
                    self.assertEqual(detail.inclination, Decimal("5.5"))
                with self.engine.begin() as connection:
                    with self.assertRaises(IntegrityError):
                        connection.execute(text(
                            f'UPDATE {model.__tablename__} SET inclination = 5.55 WHERE id = :id'
                        ), {"id": detail_id})
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])

    def test_required_fields_cannot_be_null(self):
        for model, session_type, _ in DETAIL_MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            required = set(detail_values()) - {
                "dynamic_type", "elevation_gain", "inclination", "temperature", "weather",
            }
            for field in required | {"session_id"}:
                with self.subTest(table=model.__tablename__, field=field):
                    with self.engine.begin() as connection:
                        with self.assertRaises(IntegrityError):
                            connection.execute(text(
                                f'UPDATE {model.__tablename__} SET "{field}" = NULL WHERE id = :id'
                            ), {"id": detail_id})

    def test_duration_exceeding_24_hours_and_empty_comment(self):
        detail_id, _ = self.save_detail(SessionSortieLongue, "Sortie longue")
        duration = timedelta(hours=27, minutes=15, seconds=4)
        with DatabaseSession(self.engine) as db:
            detail = db.get(SessionSortieLongue, detail_id)
            detail.Z1 = duration
            detail.comment = ""
            db.commit()
            self.assertEqual(detail.Z1, duration)
            self.assertEqual(detail.comment, "")
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT "Z1" FROM sessions_sortie_longue WHERE id = ?', (detail_id,),
            ).scalar_one(), 98104)

    def test_invalid_python_durations_are_rejected(self):
        detail_id, _ = self.save_detail(SessionSortieLongue, "Sortie longue")
        for value in (timedelta(seconds=-1), timedelta(microseconds=1), "01:02:03"):
            with self.subTest(value=value):
                with DatabaseSession(self.engine) as db:
                    detail = db.get(SessionSortieLongue, detail_id)
                    detail.Z1 = value
                    with self.assertRaises(StatementError):
                        db.commit()

    def test_foreign_keys_uniqueness_and_delete_cascade(self):
        for model, session_type, _ in DETAIL_MODELS:
            detail_id, parent_id = self.save_detail(model, session_type)
            for session_id in (parent_id, parent_id + 10000):
                with self.subTest(model=model, session_id=session_id):
                    with DatabaseSession(self.engine) as db:
                        db.add(model(session_id=session_id, **detail_values()))
                        with self.assertRaises(IntegrityError):
                            db.commit()
            with self.engine.begin() as connection:
                self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
                connection.execute(delete(Session).where(Session.id == parent_id))
            with DatabaseSession(self.engine) as db:
                self.assertIsNone(db.get(model, detail_id))

    def test_orm_delete_cascades_with_loaded_relationship(self):
        detail_id, parent_id = self.save_detail(SessionSortieLongue, "Sortie longue")
        with DatabaseSession(self.engine) as db:
            parent = db.get(Session, parent_id)
            self.assertEqual(parent.sortie_longue.id, detail_id)
            db.delete(parent)
            db.commit()
            self.assertIsNone(db.get(SessionSortieLongue, detail_id))

    def test_repeated_initialization_preserves_data(self):
        detail_id, _ = self.save_detail(SessionSortieLongue, "Sortie longue")
        initialize_database()
        initialize_database()
        with DatabaseSession(self.engine) as db:
            self.assertEqual(db.get(SessionSortieLongue, detail_id).comment, detail_values()["comment"])

    def test_storage_directory_and_direct_run_fallback(self):
        self.assertEqual(get_database_path().parent, Path(os.environ["FLET_APP_STORAGE_DATA"]))
        with patch.dict(os.environ):
            os.environ.pop("FLET_APP_STORAGE_DATA", None)
            self.assertEqual(
                get_database_path(),
                Path(__file__).resolve().parents[1] / ".flet/storage/data/trail_mania.db",
            )


if __name__ == "__main__":
    unittest.main()
