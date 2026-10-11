"""P2.2 PostgreSQL invariants, only through guarded runner preparation.

Each test uses an external transaction and rolls back all changes. Importing
or collecting this module never opens a database connection.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Appointment, Barber, Service, User
from tests.p0_database import (
    TARGET, inspect_existing_schema, require_target_url,
    test_engine as guarded_engine,
)

P22_HEAD = "0004_identity_persistence"
P0_CONSTRAINT = "ex_appointments_active_barber_time_overlap"


@pytest.fixture(scope="module")
def p22_engine():
    raw_url = os.environ.get("P0_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("P2.2 PostgreSQL not executed: P0_TEST_DATABASE_URL is unset")
    try:
        require_target_url(raw_url)
    except Exception:
        pytest.fail("P2.2 requires exactly logia_barber_p0_test with psycopg", pytrace=False)
    if os.environ.get("P0_TEST_PREPARED") != "1":
        pytest.fail("P2.2 requires the guarded runner; no automatic migration", pytrace=False)
    engine = guarded_engine(raw_url)
    engine.hide_parameters = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            if connection.scalar(text("SELECT current_database()")) != TARGET:
                raise ValueError("Wrong database")
            if list(connection.scalars(text("SELECT version_num FROM public.alembic_version"))) != [P22_HEAD]:
                raise ValueError("P2.2 requires exact revision 0004_identity_persistence")
            inspect_existing_schema(connection)
    except Exception as error:
        engine.dispose()
        pytest.fail(f"P2.2 preflight failed ({type(error).__name__}); details hidden", pytrace=False)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def p22_connection(p22_engine):
    with p22_engine.connect() as connection:
        transaction = connection.begin()
        try:
            assert connection.scalar(text("SELECT current_database()")) == TARGET
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()


@pytest.fixture
def p22_db(p22_connection):
    with Session(bind=p22_connection, join_transaction_mode="create_savepoint") as db:
        yield db


def new_user(db, role="client"):
    # Deliberately unusable marker, never a real user's password or credential.
    user = User(name="P2.2 synthetic", email=f"p22-{uuid4().hex}@example.invalid",
                password_hash="unusable-synthetic-test-marker", role=role, is_active=True)
    db.add(user)
    db.flush()
    return user


def new_booking(db, client_id=None, barber=None, offset=0, status="pending", service=None):
    if barber is None:
        barber = Barber(name=f"P2.2 {uuid4().hex}", is_active=True)
        db.add(barber)
    if service is None:
        service = Service(name=f"P2.2 {uuid4().hex}", price=10, duration_minutes=30, is_active=True)
        db.add(service)
    db.flush()
    start = datetime(2040, 1, 15, 10, tzinfo=timezone.utc) + timedelta(minutes=offset)
    row = Appointment(client_name="Historical synthetic contact", client_phone="000",
                      service_id=service.id, barber_id=barber.id,
                      client_user_id=client_id, starts_at=start,
                      ends_at=start + timedelta(minutes=30), status=status)
    db.add(row)
    db.flush()
    return row


def assert_integrity(db, action, sqlstate, constraint=None):
    with pytest.raises(IntegrityError) as caught:
        with db.begin_nested():
            action()
            db.flush()
    assert caught.value.orig.sqlstate == sqlstate
    if constraint:
        assert caught.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize("role", ["owner", "admin", "barber", "client"])
def test_four_roles_persist(p22_db, role):
    row = new_user(p22_db, role)
    p22_db.expire(row)
    assert row.role == role


@pytest.mark.parametrize("role", ["unknown", "OWNER", "", None], ids=["unknown", "case", "empty", "null"])
def test_role_constraint_rejects_invalid_values(p22_db, role):
    assert_integrity(p22_db, lambda: new_user(p22_db, role), "23502" if role is None else "23514")


def test_omitting_role_does_not_grant_barber(p22_db):
    row = User(name="P2.2", email=f"{uuid4().hex}@example.invalid",
               password_hash="unusable-test-marker", is_active=True)
    assert_integrity(p22_db, lambda: p22_db.add(row), "23502")


def test_barber_historical_nulls_and_valid_link(p22_db):
    user = new_user(p22_db, "barber")
    rows = [Barber(name="Historical A"), Barber(name="Historical B"),
            Barber(name="Linked", user_id=user.id)]
    p22_db.add_all(rows)
    p22_db.flush()
    p22_db.expire_all()
    assert [row.user_id for row in rows] == [None, None, user.id]


def test_barber_link_is_unique(p22_db):
    user = new_user(p22_db, "barber")
    p22_db.add(Barber(name="First", user_id=user.id))
    p22_db.flush()
    assert_integrity(p22_db, lambda: p22_db.add(Barber(name="Second", user_id=user.id)),
                     "23505", "uq_barbers_user_id")


def test_barber_unknown_user_rejected(p22_db):
    assert_integrity(p22_db, lambda: p22_db.add(Barber(name="Missing", user_id=-1)), "23503")


def test_appointments_preserve_historical_contact_and_allow_multiple_per_client(p22_db):
    user = new_user(p22_db)
    rows = [new_booking(p22_db), new_booking(p22_db, user.id), new_booking(p22_db, user.id)]
    p22_db.expire_all()
    assert [row.client_user_id for row in rows] == [None, user.id, user.id]
    assert all(row.client_name == "Historical synthetic contact" and row.client_phone == "000"
               for row in rows)


def test_appointment_unknown_client_rejected(p22_db):
    assert_integrity(p22_db, lambda: new_booking(p22_db, -1), "23503")


@pytest.mark.parametrize("first_status", ["pending", "confirmed"])
@pytest.mark.parametrize("second_status", ["pending", "confirmed"])
def test_identity_does_not_bypass_p0_overlap(p22_db, first_status, second_status):
    first = new_booking(p22_db, new_user(p22_db).id, status=first_status)
    barber = p22_db.get(Barber, first.barber_id)
    other = new_user(p22_db)
    assert_integrity(p22_db, lambda: new_booking(p22_db, other.id, barber, status=second_status),
                     "23P01", P0_CONSTRAINT)


@pytest.mark.parametrize("status", ["cancelled", "completed", "no_show"])
def test_inactive_status_overlap_still_allowed(p22_db, status):
    first = new_booking(p22_db, status=status)
    second = new_booking(p22_db, barber=p22_db.get(Barber, first.barber_id))
    assert first.id != second.id


def test_half_open_boundary_and_independent_barbers(p22_db):
    first = new_booking(p22_db)
    adjacent = new_booking(p22_db, barber=p22_db.get(Barber, first.barber_id), offset=30)
    independent = new_booking(p22_db)
    assert len({first.id, adjacent.id, independent.id}) == 3


def new_session(db, user_id, token_hash=None):
    model = importlib.import_module("app.models.models").AuthSession
    row = model(user_id=user_id,
                session_token_hash=token_hash or hashlib.sha256(uuid4().bytes).hexdigest(),
                csrf_token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add(row)
    db.flush()
    return row


def test_session_timestamps_and_revocation_persist(p22_db):
    row = new_session(p22_db, new_user(p22_db).id)
    expires = row.expires_at
    p22_db.expire(row)
    assert row.expires_at == expires and row.expires_at.tzinfo is not None
    assert row.created_at is not None and row.created_at.tzinfo is not None
    assert row.revoked_at is None
    revoked = datetime.now(timezone.utc)
    row.revoked_at = revoked
    p22_db.flush()
    p22_db.expire(row)
    assert row.revoked_at == revoked


def test_session_hash_unique(p22_db):
    user = new_user(p22_db)
    first = new_session(p22_db, user.id)
    assert_integrity(p22_db, lambda: new_session(p22_db, user.id, first.session_token_hash),
                     "23505", "uq_auth_sessions_session_token_hash")


def test_session_unknown_user_rejected(p22_db):
    assert_integrity(p22_db, lambda: new_session(p22_db, -1), "23503")


@pytest.mark.parametrize("field", ["user_id", "session_token_hash", "csrf_token_hash", "expires_at"])
def test_session_required_fields(p22_db, field):
    row = new_session(p22_db, new_user(p22_db).id)
    assert_integrity(p22_db, lambda: setattr(row, field, None), "23502")


@pytest.mark.parametrize("relation", ["barber", "appointment", "session"])
def test_user_delete_restrict_preserves_referencing_data(p22_db, relation):
    user = new_user(p22_db, "barber" if relation == "barber" else "client")
    if relation == "barber":
        p22_db.add(Barber(name="Restricted", user_id=user.id))
        p22_db.flush()
    elif relation == "appointment":
        new_booking(p22_db, user.id)
    else:
        new_session(p22_db, user.id)
    user_id = user.id
    # DELETE RESTRICT raises restrict_violation; missing-parent INSERTs use 23503.
    assert_integrity(p22_db, lambda: p22_db.execute(delete(User).where(User.id == user_id)), "23001")
    assert p22_db.scalar(select(User.id).where(User.id == user_id)) == user_id


def test_session_storage_has_no_raw_secret_columns(p22_connection):
    columns = {column["name"]: column for column in inspect(p22_connection).get_columns("auth_sessions")}
    assert set(columns) == {"id", "user_id", "session_token_hash", "csrf_token_hash",
                            "created_at", "expires_at", "revoked_at"}
    assert all(columns[name]["type"].length == 64 for name in ("session_token_hash", "csrf_token_hash"))


def test_real_token_helpers_store_only_independent_digests(p22_db):
    from app.core.credentials import generate_token, hash_token
    from app.models.models import AuthSession

    session_token, csrf_token = generate_token(), generate_token()
    row = AuthSession(user_id=new_user(p22_db).id,
                      session_token_hash=hash_token(session_token),
                      csrf_token_hash=hash_token(csrf_token),
                      expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    p22_db.add(row)
    p22_db.flush()
    p22_db.expire(row)
    assert bool(row.session_token_hash == hashlib.sha256(session_token.encode()).hexdigest())
    assert bool(row.csrf_token_hash == hashlib.sha256(csrf_token.encode()).hexdigest())
    assert bool(row.session_token_hash != session_token and row.csrf_token_hash != csrf_token)
    assert bool(row.session_token_hash != row.csrf_token_hash)
