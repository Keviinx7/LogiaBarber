"""Real PostgreSQL only, on the exact target prepared by run_p0_validation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from types import SimpleNamespace
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.routes.public import BUSINESS_TZ
from app.core.config import settings
from app.main import app
from app.models import Appointment, Barber, BusinessHours, Service
from tests.p0_database import HEAD, TARGET, test_engine as guarded_engine

CONSTRAINT = "ex_appointments_active_barber_time_overlap"


@pytest.fixture(scope="module")
def pg_engine():
    raw_url = os.environ.get("P0_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("P0_TEST_DATABASE_URL is unset; real PostgreSQL tests not executed")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.database != TARGET
        or url.database == make_url(settings.database_url).database
    ):
        pytest.fail("P0 requires exactly logia_barber_p0_test, separate from the current DB", pytrace=False)
    if os.environ.get("P0_TEST_PREPARED") != "1":
        pytest.fail("Run the guarded P0 validation runner first; no automatic migration", pytrace=False)
    engine = guarded_engine(raw_url)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TARGET:
                pytest.fail("Actual database is not logia_barber_p0_test", pytrace=False)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    except Exception as error:
        engine.dispose()
        pytest.fail(f"Test DB preflight failed ({type(error).__name__}); connection details hidden", pytrace=False)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def booking(pg_engine):
    tag = uuid4().hex
    start = (datetime.now(BUSINESS_TZ) + timedelta(days=7)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    with Session(pg_engine) as db:
        service = Service(name=f"P0 {tag}", price=10, duration_minutes=60, is_active=True)
        barbers = [Barber(name=f"P0 {tag} {i}", is_active=True) for i in range(2)]
        db.add_all([service, *barbers])
        db.flush()
        service_id, barber_ids = service.id, [barber.id for barber in barbers]
        for barber in barbers:
            db.add(BusinessHours(
                barber_id=barber.id, day_of_week=start.weekday(),
                opening_time=time(8), closing_time=time(18), is_open=True,
            ))
        db.commit()
    try:
        yield SimpleNamespace(service_id=service_id, barber_ids=barber_ids, start=start)
    finally:
        # Delete only the rows owned by this test, exclusively in the guarded DB.
        with Session(pg_engine) as db:
            db.execute(delete(Appointment).where(Appointment.service_id == service_id))
            db.execute(delete(BusinessHours).where(BusinessHours.barber_id.in_(barber_ids)))
            db.execute(delete(Barber).where(Barber.id.in_(barber_ids)))
            db.execute(delete(Service).where(Service.id == service_id))
            db.commit()


def appointment(booking, *, barber=None, start=0, end=60, status="pending"):
    return Appointment(
        client_name="P0 test", client_phone="000", service_id=booking.service_id,
        barber_id=booking.barber_ids[0] if barber is None else barber,
        starts_at=booking.start + timedelta(minutes=start),
        ends_at=booking.start + timedelta(minutes=end), status=status,
    )


def payload(booking, barber, offset=0):
    return {
        "client_name": "P0 test", "client_phone": "000",
        "service_id": booking.service_id, "barber_id": barber,
        "starts_at": (booking.start + timedelta(minutes=offset)).isoformat(),
    }


def persisted_count(engine, booking):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Appointment).where(
            Appointment.service_id == booking.service_id
        ))


def test_migrated_database_at_head(pg_engine):
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='btree_gist'"))
        constraints = connection.execute(text("""
            SELECT conname, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint WHERE conrelid='public.appointments'::regclass AND contype='x'
        """)).all()
        assert len(constraints) == 1
        name, definition = constraints[0]
        assert name == CONSTRAINT
        assert not connection.scalar(text("""
            SELECT count(*) FROM pg_constraint
            WHERE conrelid='public.appointments'::regclass
              AND conname='ex_appointments_active_time_overlap'
        """))
        assert "barber_id WITH =" in definition
        assert "tstzrange(starts_at, ends_at, '[)'::text) WITH &&" in definition
        assert "pending" in definition and "confirmed" in definition
        assert connection.scalar(text("""
            SELECT attnotnull FROM pg_attribute
            WHERE attrelid='public.appointments'::regclass AND attname='barber_id'
        """))


@pytest.mark.parametrize("first_status", ["pending", "confirmed"])
@pytest.mark.parametrize("second_status", ["pending", "confirmed"])
@pytest.mark.parametrize("start,end", [
    (-30, 30), (30, 90), (15, 45), (-30, 90), (0, 60),
], ids=["partial-left", "partial-right", "contained", "contains", "identical"])
def test_same_barber_active_overlaps_rejected(pg_engine, booking, first_status, second_status, start, end):
    with Session(pg_engine) as db:
        db.add(appointment(booking, status=first_status))
        db.commit()
        db.add(appointment(booking, start=start, end=end, status=second_status))
        with pytest.raises(IntegrityError) as caught:
            db.commit()
        assert caught.value.orig.sqlstate == "23P01"
        assert caught.value.orig.diag.constraint_name == CONSTRAINT
        db.rollback()
    assert persisted_count(pg_engine, booking) == 1


def test_different_barbers_same_interval_allowed(pg_engine, booking):
    with Session(pg_engine) as db:
        db.add_all([appointment(booking, barber=barber) for barber in booking.barber_ids])
        db.commit()
    assert persisted_count(pg_engine, booking) == 2


@pytest.mark.parametrize("start,end", [(-60, 0), (60, 120)])
def test_adjacent_intervals_allowed(pg_engine, booking, start, end):
    with Session(pg_engine) as db:
        db.add_all([appointment(booking), appointment(booking, start=start, end=end)])
        db.commit()
    assert persisted_count(pg_engine, booking) == 2


@pytest.mark.parametrize("inactive", ["cancelled", "completed", "no_show"])
@pytest.mark.parametrize("inactive_first", [True, False])
def test_inactive_statuses_do_not_block(pg_engine, booking, inactive, inactive_first):
    statuses = [inactive, "pending"] if inactive_first else ["confirmed", inactive]
    with Session(pg_engine) as db:
        for status in statuses:
            db.add(appointment(booking, status=status))
            db.commit()
    assert persisted_count(pg_engine, booking) == 2


@pytest.fixture
def client_factory(pg_engine):
    original_overrides = app.dependency_overrides.copy()
    clients = []

    def factory(session_class=Session, shared_session=None):
        def override_db():
            if shared_session is not None:
                yield shared_session
            else:
                with session_class(pg_engine) as db:
                    yield db
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=False)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.mark.parametrize("different_barbers", [False, True], ids=["same-barber", "different-barbers"])
@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_posts(pg_engine, booking, client_factory, different_barbers, attempt):
    before_lock, after_lock = Barrier(2), Barrier(2)

    class SynchronizedSession(Session):
        def scalar(self, statement, *args, **kwargs):
            # Both requests have real transactions and reach the lock together.
            is_barber_lock = statement._for_update_arg is not None
            if is_barber_lock:
                before_lock.wait(timeout=8)
            value = super().scalar(statement, *args, **kwargs)
            if is_barber_lock and different_barbers:
                # Both must hold their locks simultaneously. A global lock would
                # deadlock this barrier and fail instead of passing sequentially.
                after_lock.wait(timeout=8)
            return value

    client = client_factory(SynchronizedSession)
    barbers = booking.barber_ids if different_barbers else [booking.barber_ids[0]] * 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, "/api/appointments", json=payload(booking, barber)) for barber in barbers]
        responses = [future.result(timeout=25) for future in futures]
    expected = [201, 201] if different_barbers else [201, 409]
    actual = sorted(response.status_code for response in responses)
    count = persisted_count(pg_engine, booking)
    assert actual == expected
    assert count == (2 if different_barbers else 1)
    print(f"P0 race: different_barbers={different_barbers}, attempt={attempt}, HTTP={actual}, persisted={count}")


def test_valid_post_after_409_reuses_session(pg_engine, booking, client_factory):
    with Session(pg_engine) as db:
        client = client_factory(shared_session=db)
        body = payload(booking, booking.barber_ids[0])
        assert client.post("/api/appointments", json=body).status_code == 201
        assert client.post("/api/appointments", json=body).status_code == 409
        assert not db.in_transaction()
        adjacent = payload(booking, booking.barber_ids[0], offset=60)
        assert client.post("/api/appointments", json=adjacent).status_code == 201
    assert persisted_count(pg_engine, booking) == 2


def test_actual_foreign_key_error_is_not_409(pg_engine, booking, client_factory):
    errors = []

    class InvalidForeignKeySession(Session):
        def commit(self):
            for obj in self.new:
                if isinstance(obj, Appointment):
                    obj.service_id = -1
            try:
                super().commit()
            except IntegrityError as error:
                errors.append(error.orig.sqlstate)
                raise

    client = client_factory(InvalidForeignKeySession)
    response = client.post("/api/appointments", json=payload(booking, booking.barber_ids[0]))
    assert errors == ["23503"]
    assert response.status_code == 500  # Unexpected failures retain their real classification.
    assert persisted_count(pg_engine, booking) == 0
