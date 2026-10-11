"""Offline checks: no database connection or SQLite substitutes."""
from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateTable

from app.api.routes import public
from app.core.config import settings
from app.models import Appointment
from app.schemas import AppointmentCreate

BACKEND = Path(__file__).resolve().parents[1]
CONSTRAINT = "ex_appointments_active_barber_time_overlap"


def migration_sql(monkeypatch, direction):
    # Offline Alembic compiles PostgreSQL DDL without connecting to any server.
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://offline/offline")
    output = StringIO()
    config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    if direction == "upgrade":
        # P0's approved prefix stays compilable offline. P2.2 separately tests
        # 0004 online because its default/data inspection cannot be done offline.
        command.upgrade(config, "0003_barbers_and_schedules", sql=True)
    else:
        # Deliberately stop at 0002; its downgrade is outside P0 scope.
        command.downgrade(config, "0003_barbers_and_schedules:0002_overlap_constraint", sql=True)
    return output.getvalue()


def test_p0_upgrade_ddl_and_model_agree(monkeypatch):
    ddl = migration_sql(monkeypatch, "upgrade")
    expected = (
        f"CONSTRAINT {CONSTRAINT} EXCLUDE USING gist "
        "(barber_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) "
        "WHERE (status IN ('pending', 'confirmed'))"
    )
    assert expected in ddl
    assert expected in str(CreateTable(Appointment.__table__).compile(dialect=postgresql.dialect()))
    drop = "ALTER TABLE appointments DROP CONSTRAINT ex_appointments_active_time_overlap;"
    assert drop in ddl
    assert ddl.index(drop) < ddl.index(expected)
    assert "WITH = WITH =" not in ddl


def test_0003_downgrade_ddl(monkeypatch):
    ddl = migration_sql(monkeypatch, "downgrade")
    assert f"DROP CONSTRAINT {CONSTRAINT};" in ddl
    assert "ADD CONSTRAINT ex_appointments_active_time_overlap EXCLUDE USING gist" in ddl
    assert "barber_id WITH =" not in ddl


class DatabaseFailure(Exception):
    def __init__(self, sqlstate, constraint):
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(constraint_name=constraint)

    def __str__(self):
        raise AssertionError("Conflict handling must not inspect exception text")


def booking_session():
    starts_at = (datetime.now(public.BUSINESS_TZ) + timedelta(days=7)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    payload = AppointmentCreate(
        client_name="P0 test", client_phone="000", service_id=1,
        barber_id=2, starts_at=starts_at,
    )
    db = MagicMock()
    db.scalar.side_effect = [
        SimpleNamespace(duration_minutes=30), SimpleNamespace(id=2),
        SimpleNamespace(is_open=True, opening_time=time(8), closing_time=time(18)),
        None,
    ]
    return payload, db


def test_expected_integrity_error_rolls_back_before_409():
    payload, db = booking_session()
    db.commit.side_effect = IntegrityError(None, None, DatabaseFailure("23P01", CONSTRAINT))
    with pytest.raises(HTTPException) as caught:
        public.create_appointment(payload, db)
    assert caught.value.status_code == 409
    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()
    lock_query = db.scalar.call_args_list[1].args[0]
    sql = str(lock_query.compile(dialect=postgresql.dialect()))
    assert "FOR NO KEY UPDATE" in sql
    assert "barbers.id =" in sql


@pytest.mark.parametrize("sqlstate,constraint", [
    ("23505", CONSTRAINT),
    ("23503", "appointments_service_id_fkey"),
    ("23514", "ck_appointments_time_order"),
    ("23P01", "some_other_exclusion"),
    ("23P01", "ex_appointments_active_time_overlap"),
    (None, CONSTRAINT),
    ("23P01", None),
])
def test_other_integrity_errors_propagate(sqlstate, constraint):
    payload, db = booking_session()
    error = IntegrityError(None, None, DatabaseFailure(sqlstate, constraint))
    db.commit.side_effect = error
    with pytest.raises(IntegrityError) as caught:
        public.create_appointment(payload, db)
    assert caught.value is error
    db.rollback.assert_called_once_with()


def test_other_postgresql_errors_propagate():
    payload, db = booking_session()
    error = OperationalError(None, None, DatabaseFailure("40P01", None))
    db.commit.side_effect = error
    with pytest.raises(OperationalError) as caught:
        public.create_appointment(payload, db)
    assert caught.value is error
    db.rollback.assert_called_once_with()


def test_validation_releases_barber_lock():
    payload, db = booking_session()
    payload.starts_at -= timedelta(days=8)
    with pytest.raises(HTTPException) as caught:
        public.create_appointment(payload, db)
    assert caught.value.status_code == 422
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()
