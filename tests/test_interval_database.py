import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.database import create_database_engine, initialize_database
from trail_mania.models import Session, SessionSeuil, SessionVO2max


MODELS = (
    (SessionSeuil, "Seuil", "seuil"),
    (SessionVO2max, "VO2max", "vo2max"),
)
COMMON_OPTIONAL = {
    "dynamic_type", "duration_OFF", "inclination", "elevation_gain", "temperature", "weather",
}
OPTIONAL = {
    SessionSeuil: COMMON_OPTIONAL | {
        "velocity_OFF_1", "velocity_ON_2", "velocity_OFF_2", "velocity_ON_3",
        "mean_HR_ON_2", "max_HR_ON_2", "mean_HR_ON_3", "max_HR_ON_3",
    },
    SessionVO2max: COMMON_OPTIONAL | {
        "velocity_OFF_4", "velocity_ON_5", "velocity_OFF_5", "velocity_ON_6",
        "mean_HR_ON_5", "max_HR_ON_5", "mean_HR_ON_6", "max_HR_ON_6",
    },
}


def interval_values(model):
    values = dict(
        field_type="Tapis", slope_type="Avec pente", dynamic_type="Course",
        duration_ON=Decimal("10.5"), duration_OFF=Decimal("2.5"),
        inclination=Decimal("5.5"), elevation_gain=200, temperature=-3,
        weather="Vent & pluie", RPE=Decimal("7.5"), comment="Séance\nÀ refaire !",
        Z1=timedelta(hours=25, minutes=2, seconds=3), Z2=timedelta(minutes=20),
        Z3=timedelta(minutes=15), Z4=timedelta(minutes=10), Z5=timedelta(0),
    )
    repetitions = 3 if model is SessionSeuil else 6
    for index in range(1, repetitions + 1):
        values[f"velocity_ON_{index}"] = 12.345 + index
        values[f"mean_HR_ON_{index}"] = 150 + index
        values[f"max_HR_ON_{index}"] = 175 + index
        if index < repetitions:
            values[f"velocity_OFF_{index}"] = 8.765 + index
    return values


class IntervalDatabaseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {
            "FLET_APP_STORAGE_DATA": str(Path(directory.name) / "data"),
        }))
        initialize_database()
        self.engine = create_database_engine()
        self.addCleanup(self.engine.dispose)

    def save_detail(self, model, session_type, minimal=False):
        values = interval_values(model)
        if minimal:
            values = {name: value for name, value in values.items() if name not in OPTIONAL[model]}
        with DatabaseSession(self.engine) as db:
            parent = Session(date=date(2026, 11, 3), session_type=session_type)
            detail = model(session=parent, **values)
            db.add(detail)
            db.commit()
            return detail.id, parent.id

    def test_schema_matches_requested_columns_and_nullability(self):
        inspector = inspect(self.engine)
        for model, _, _ in MODELS:
            with self.subTest(model=model):
                columns = inspector.get_columns(model.__tablename__)
                self.assertEqual(
                    {column["name"] for column in columns},
                    {"id", "session_id", *interval_values(model)},
                )
                self.assertEqual(
                    {column["name"] for column in columns if column["nullable"]},
                    OPTIONAL[model],
                )

    def test_full_and_minimal_sessions_round_trip(self):
        for model, session_type, relation in MODELS:
            for minimal in (False, True):
                with self.subTest(model=model, minimal=minimal):
                    detail_id, parent_id = self.save_detail(model, session_type, minimal)
                    with DatabaseSession(self.engine) as db:
                        detail = db.get(model, detail_id)
                        parent = db.get(Session, parent_id)
                        self.assertIs(detail.session, parent)
                        self.assertIs(getattr(parent, relation), detail)
                        self.assertEqual(parent.session_type, session_type)
                        self.assertIsInstance(detail.duration_ON, Decimal)
                        self.assertIsInstance(detail.velocity_ON_1, float)
                        for name, value in interval_values(model).items():
                            expected = None if minimal and name in OPTIONAL[model] else value
                            self.assertEqual(getattr(detail, name), expected)

    def test_required_fields_cannot_be_null(self):
        for model, session_type, _ in MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            required = {"session_id", *interval_values(model)} - OPTIONAL[model]
            for field in required:
                with self.subTest(model=model, field=field):
                    with self.engine.begin() as connection:
                        with self.assertRaises(IntegrityError):
                            connection.execute(text(
                                f'UPDATE {model.__tablename__} SET "{field}" = NULL WHERE id = :id'
                            ), {"id": detail_id})

    def test_invalid_choices_precision_integer_values_and_durations_are_rejected(self):
        for model, session_type, _ in MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            invalid = {
                "field_type": "Inconnu", "slope_type": "Inconnu",
                "dynamic_type": "Inconnu", "weather": "Inconnu",
                "duration_ON": 10.55, "duration_OFF": 2.55,
                "inclination": 5.55, "RPE": 7.55,
                "elevation_gain": 1.5, "temperature": 1.5,
            }
            for field in interval_values(model):
                if field.startswith(("mean_HR_", "max_HR_")):
                    invalid[field] = 150.5
                if field in ("Z1", "Z2", "Z3", "Z4", "Z5"):
                    invalid[field] = -1
            for field, value in invalid.items():
                with self.subTest(model=model, field=field):
                    with self.engine.begin() as connection:
                        with self.assertRaises(IntegrityError):
                            connection.execute(text(
                                f'UPDATE {model.__tablename__} SET "{field}" = :value WHERE id = :id'
                            ), {"value": value, "id": detail_id})

    def test_allowed_choices(self):
        choices = {
            "field_type": ("Route", "Terrain roulant", "Terrain technique", "Tapis"),
            "slope_type": ("Sans pente", "Avec pente"),
            "dynamic_type": ("Marche", "Course", None),
            "weather": ("Normal", "Vent", "Pluie", "Vent & pluie"),
        }
        for model, session_type, _ in MODELS:
            detail_id, _ = self.save_detail(model, session_type)
            for field, values in choices.items():
                for value in values:
                    with self.subTest(model=model, field=field, value=value):
                        with DatabaseSession(self.engine) as db:
                            detail = db.get(model, detail_id)
                            setattr(detail, field, value)
                            db.commit()
                            self.assertEqual(getattr(detail, field), value)

    def test_foreign_keys_uniqueness_and_database_delete_cascade(self):
        for model, session_type, _ in MODELS:
            detail_id, parent_id = self.save_detail(model, session_type)
            for session_id in (parent_id, parent_id + 10000):
                with self.subTest(model=model, session_id=session_id):
                    with DatabaseSession(self.engine) as db:
                        db.add(model(session_id=session_id, **interval_values(model)))
                        with self.assertRaises(IntegrityError):
                            db.commit()
            with self.engine.begin() as connection:
                connection.execute(delete(Session).where(Session.id == parent_id))
            with DatabaseSession(self.engine) as db:
                self.assertIsNone(db.get(model, detail_id))

    def test_orm_delete_cascade_with_loaded_and_unloaded_relationship(self):
        for model, session_type, relation in MODELS:
            for loaded in (False, True):
                with self.subTest(model=model, loaded=loaded):
                    detail_id, parent_id = self.save_detail(model, session_type)
                    with DatabaseSession(self.engine) as db:
                        parent = db.get(Session, parent_id)
                        if loaded:
                            self.assertEqual(getattr(parent, relation).id, detail_id)
                        db.delete(parent)
                        db.commit()
                        self.assertIsNone(db.get(model, detail_id))

    def test_initialization_preserves_interval_sessions(self):
        saved = [(model, *self.save_detail(model, session_type)) for model, session_type, _ in MODELS]
        initialize_database()
        initialize_database()
        for model, detail_id, parent_id in saved:
            with self.subTest(model=model):
                with DatabaseSession(self.engine) as db:
                    detail = db.get(model, detail_id)
                    self.assertEqual(detail.session_id, parent_id)
                    for field, value in interval_values(model).items():
                        self.assertEqual(getattr(detail, field), value)


if __name__ == "__main__":
    unittest.main()
