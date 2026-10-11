"""P2.2 migration contracts and transactional PostgreSQL migration tests.

Real DDL runs only in a private schema in the exact guarded test database.
The outer transaction always rolls back the schema and all its rows; public
tables, sessions and alembic_version never undergo downgrade or deletion.
"""
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.dialects import postgresql

from app.models.models import Appointment, Barber, User
from tests.test_p22_postgresql import p22_connection, p22_engine  # noqa: F401

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
HEAD = "0004_identity_persistence"
PREVIOUS = "0003_barbers_and_schedules"
CONSTRAINT = "ex_appointments_active_barber_time_overlap"


def migration(filename):
    spec = importlib.util.spec_from_file_location(f"p22_test_{filename[:-3]}", VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity_migration():
    return migration("0004_identity_persistence.py")


def run_migration(connection, module, direction):
    # Do not call Alembic env.py: it could open a separate, committing engine.
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        getattr(module, direction)()


def test_revision_is_exact_successor_of_0003():
    module = identity_migration()
    assert module.revision == HEAD
    assert module.down_revision == PREVIOUS
    assert callable(module.upgrade) and callable(module.downgrade)
    assert module.branch_labels is None and module.depends_on is None


def mocked_operations(monkeypatch, *, role_default=None, incompatible=False, offline=False):
    """Simulate Alembic orchestration only, never credential primitives."""
    module = identity_migration()
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = incompatible
    operations = MagicMock()
    operations.get_context.return_value = SimpleNamespace(as_sql=offline)
    operations.get_bind.return_value = connection
    inspector = MagicMock()
    inspector.get_columns.return_value = [{"name": "role", "default": role_default}]
    monkeypatch.setattr(module, "op", operations)
    inspect_mock = MagicMock(return_value=inspector)
    monkeypatch.setattr(module.sa, "inspect", inspect_mock)
    return module, operations, connection, inspector


@pytest.mark.parametrize("role_default", [None, "'barber'::character varying"],
                         ids=["absent", "existing"])
def test_unit_upgrade_only_drops_a_real_role_default(monkeypatch, role_default):
    module, operations, connection, inspector = mocked_operations(monkeypatch, role_default=role_default)
    module.upgrade()
    inspector.get_columns.assert_called_once_with("users")
    if role_default is None:
        operations.alter_column.assert_not_called()
    else:
        operations.alter_column.assert_called_once_with("users", "role", server_default=None)
    operations.create_check_constraint.assert_called_once_with(
        "ck_users_role", "users", "role IN ('owner', 'admin', 'barber', 'client')",
    )
    operations.drop_constraint.assert_called_once_with("ck_users_role", "users", type_="check")
    assert [call.args[0] for call in operations.add_column.call_args_list] == ["barbers", "appointments"]
    operations.drop_table.assert_not_called()
    operations.drop_column.assert_not_called()
    connection.execute.assert_not_called()  # No invented backfill or writes.


def test_unit_downgrade_incompatible_roles_refuses_all_ddl(monkeypatch):
    module, operations, connection, _ = mocked_operations(monkeypatch, incompatible=True)
    with pytest.raises(RuntimeError, match="incompatible"):
        module.downgrade()
    assert [call[0] for call in operations.mock_calls if "." not in call[0]] == ["get_context", "get_bind"]
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[0] == "LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"
    assert statements[1] == "SELECT EXISTS (SELECT 1 FROM users WHERE role NOT IN ('admin', 'barber'))"


def test_unit_downgrade_removes_only_p22_structures(monkeypatch):
    module, operations, _, _ = mocked_operations(monkeypatch)
    module.downgrade()
    operations.drop_table.assert_called_once_with("auth_sessions")
    assert [call.args for call in operations.drop_column.call_args_list] == [
        ("appointments", "client_user_id"), ("barbers", "user_id"),
    ]
    dropped_constraints = {call.args[0] for call in operations.drop_constraint.call_args_list}
    assert dropped_constraints == {
        "fk_appointments_client_user_id", "uq_barbers_user_id", "fk_barbers_user_id", "ck_users_role",
    }
    assert CONSTRAINT not in dropped_constraints
    operations.create_check_constraint.assert_called_once_with(
        "ck_users_role", "users", "role IN ('admin', 'barber')",
    )


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_unit_offline_migration_refuses_unverified_changes(monkeypatch, direction):
    module, operations, _, _ = mocked_operations(monkeypatch, offline=True)
    with pytest.raises(RuntimeError, match="online schema inspection"):
        getattr(module, direction)()
    assert [call[0] for call in operations.mock_calls] == ["get_context"]


@pytest.fixture
def migration_sandbox(p22_connection):
    connection = p22_connection
    schema = "p22_migration_" + uuid4().hex
    # Identifier is constructed exclusively from a fixed prefix and hex UUID.
    # CREATE SCHEMA and all DDL are rolled back by p22_connection even on error.
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    for filename in (
        "0001_initial_persistence.py",
        "0002_appointment_overlap_constraint.py",
        "0003_barbers_and_schedules.py",
    ):
        run_migration(connection, migration(filename), "upgrade")
    assert connection.scalar(text("SELECT current_schema()")) == schema
    yield connection, schema


def constraint_snapshot(connection, schema):
    return [tuple(row) for row in connection.execute(text("""
        SELECT c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class t ON c.conrelid=t.oid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=:schema AND t.relname='appointments'
          AND c.conname NOT LIKE '%client_user%'
        ORDER BY c.conname
    """), {"schema": schema})]


def insert_legacy_data(connection):
    for role in ("admin", "barber"):
        connection.execute(text("""
            INSERT INTO users (name, email, password_hash, role, is_active)
            VALUES (:name, :email, :hash, :role, true)
        """), {"name": "Historical synthetic " + role, "email": role + "@example.invalid",
               "hash": "unusable-synthetic-test-marker", "role": role})
    service_id = connection.scalar(text("""
        INSERT INTO services (name, price, duration_minutes, is_active)
        VALUES ('Historical synthetic service', 10, 30, true) RETURNING id
    """))
    barber_id = connection.scalar(text("SELECT min(id) FROM barbers"))
    connection.execute(text("""
        INSERT INTO appointments
            (client_name, client_phone, service_id, barber_id, starts_at, ends_at, status)
        VALUES ('Historical synthetic client', '000', :service, :barber,
                '2040-01-15T10:00:00+00:00', '2040-01-15T10:30:00+00:00', 'pending')
    """), {"service": service_id, "barber": barber_id})


def legacy_snapshot(connection):
    # Hashes are compared only as opaque data; snapshots are never logged.
    return {table: [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))]
            for table in ("users", "barbers", "appointments", "services", "business_hours", "blocked_times")}


def test_upgrade_and_downgrade_preserve_historical_rows_and_p0(migration_sandbox):
    connection, schema = migration_sandbox
    insert_legacy_data(connection)
    before = legacy_snapshot(connection)
    columns_before = {table: [c["name"] for c in inspect(connection).get_columns(table, schema=schema)]
                      for table in before}
    p0_before = constraint_snapshot(connection, schema)
    module = identity_migration()
    run_migration(connection, module, "upgrade")
    for table, expected in before.items():
        fields = ", ".join(columns_before[table])
        rows = [tuple(row) for row in connection.execute(text(f"SELECT {fields} FROM {table} ORDER BY id"))]
        assert bool(rows == expected), f"Historical rows changed in {table}"
    assert connection.scalar(text("SELECT count(*) FROM appointments WHERE client_user_id IS NULL")) == 1
    assert connection.scalar(text("SELECT count(*) FROM barbers WHERE user_id IS NOT NULL")) == 0
    assert constraint_snapshot(connection, schema) == p0_before
    assert inspect(connection).has_table("auth_sessions", schema=schema)
    assert next(c for c in inspect(connection).get_columns("appointments", schema=schema)
                if c["name"] == "barber_id")["nullable"] is False
    # Downgrade may remove P2-only session rows; historical users/reservations
    # must survive. These rows exist only in the rollback-isolated schema.
    connection.execute(text("""
        INSERT INTO auth_sessions (user_id, session_token_hash, csrf_token_hash, expires_at)
        SELECT id, repeat('a', 64), repeat('b', 64), now() + interval '1 hour'
        FROM users WHERE role='admin'
    """))
    run_migration(connection, module, "downgrade")
    assert not inspect(connection).has_table("auth_sessions", schema=schema)
    assert bool(legacy_snapshot(connection) == before), "Downgrade altered historical data"
    assert constraint_snapshot(connection, schema) == p0_before
    for table, expected in columns_before.items():
        assert [c["name"] for c in inspect(connection).get_columns(table, schema=schema)] == expected
    checks = inspect(connection).get_check_constraints("users", schema=schema)
    role_check = next(c["sqltext"] for c in checks if c["name"] == "ck_users_role")
    assert set(re.findall(r"'([^']+)'", role_check)) == {"admin", "barber"}
    # A subsequent upgrade is valid and does not rely on pre-existing P2 DDL.
    run_migration(connection, module, "upgrade")
    assert inspect(connection).has_table("auth_sessions", schema=schema)
    assert constraint_snapshot(connection, schema) == p0_before


@pytest.mark.parametrize("role", ["owner", "client"])
def test_downgrade_refuses_new_roles_before_any_ddl(migration_sandbox, role):
    from sqlalchemy import event

    connection, schema = migration_sandbox
    module = identity_migration()
    run_migration(connection, module, "upgrade")
    connection.execute(text("""
        INSERT INTO users (name, email, password_hash, role, is_active)
        VALUES ('Synthetic protected user', 'protected@example.invalid', :hash, :role, true)
    """), {"hash": "unusable-synthetic-test-marker", "role": role})
    connection.execute(text("""
        INSERT INTO auth_sessions (user_id, session_token_hash, csrf_token_hash, expires_at)
        SELECT id, repeat('a', 64), repeat('b', 64), now() + interval '1 hour'
        FROM users WHERE email='protected@example.invalid'
    """))
    ddl = []

    def record_ddl(conn, cursor, statement, parameters, context, executemany):
        if re.search(r"\b(?:ALTER|DROP|CREATE|TRUNCATE|DELETE|UPDATE)\b", statement, re.I):
            ddl.append(True)  # Do not record SQL parameters or secret material.

    event.listen(connection, "before_cursor_execute", record_ddl)
    try:
        with pytest.raises((RuntimeError, ValueError)):
            run_migration(connection, module, "downgrade")
    finally:
        event.remove(connection, "before_cursor_execute", record_ddl)
    assert not ddl, "Downgrade must refuse incompatible roles before mutating schema/data"
    assert connection.scalar(text("SELECT role FROM users WHERE email='protected@example.invalid'")) == role
    assert inspect(connection).has_table("auth_sessions", schema=schema)
    assert connection.scalar(text("SELECT count(*) FROM auth_sessions")) == 1
    assert "user_id" in {c["name"] for c in inspect(connection).get_columns("barbers", schema=schema)}
    assert "client_user_id" in {c["name"] for c in inspect(connection).get_columns("appointments", schema=schema)}


def column_signature(column):
    type_ = column["type"]
    return (str(type_.compile(dialect=postgresql.dialect())), column["nullable"])


def test_0004_model_and_ddl_agree_without_asserting_preexisting_drift(migration_sandbox):
    from app.models.models import AuthSession

    connection, schema = migration_sandbox
    run_migration(connection, identity_migration(), "upgrade")
    inspector = inspect(connection)
    # Only new fields/new table and the deliberately changed role contract are
    # compared. Legacy index/default drift in 0001-0003 is outside this change.
    for model, names in (
        (User, ["role"]), (Barber, ["user_id"]), (Appointment, ["client_user_id"]),
        (AuthSession, list(AuthSession.__table__.c.keys())),
    ):
        actual = {c["name"]: c for c in inspector.get_columns(model.__tablename__, schema=schema)}
        for name in names:
            column = model.__table__.c[name]
            assert column_signature(actual[name]) == column_signature({
                "type": column.type, "nullable": column.nullable,
            })
        if model is AuthSession:
            assert set(actual) == set(names)
            assert inspector.get_pk_constraint(model.__tablename__, schema=schema)["constrained_columns"] == ["id"]
            assert "now()" in actual["created_at"]["default"]
        if model is User:
            assert actual["role"]["default"] is None
            actual_check = next(c["sqltext"] for c in inspector.get_check_constraints("users", schema=schema)
                                if c["name"] == "ck_users_role")
            model_check = next(str(c.sqltext) for c in User.__table__.constraints
                               if isinstance(c, CheckConstraint) and c.name == "ck_users_role")
            assert set(re.findall(r"'([^']+)'", actual_check)) == set(re.findall(r"'([^']+)'", model_check))
    for table, column in (("barbers", "user_id"), ("appointments", "client_user_id"),
                          ("auth_sessions", "user_id")):
        fk, = [fk for fk in inspector.get_foreign_keys(table, schema=schema)
               if fk["constrained_columns"] == [column]]
        assert fk["referred_table"] == "users"
        assert fk["referred_columns"] == ["id"]
        assert fk["options"].get("ondelete") == "RESTRICT"
    for table, name, column in (
        ("barbers", "uq_barbers_user_id", "user_id"),
        ("auth_sessions", "uq_auth_sessions_session_token_hash", "session_token_hash"),
    ):
        unique = next(c for c in inspector.get_unique_constraints(table, schema=schema) if c["name"] == name)
        assert unique["column_names"] == [column]
    assert any(index["column_names"] == ["user_id"]
               for index in inspector.get_indexes("auth_sessions", schema=schema))


@pytest.mark.parametrize("has_server_default", [False, True], ids=["no-default", "legacy-server-default"])
def test_upgrade_removes_only_an_existing_role_server_default(migration_sandbox, has_server_default):
    from sqlalchemy import event

    connection, schema = migration_sandbox
    if has_server_default:
        connection.execute(text("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'barber'"))
    default_alters = []

    def record_default_change(conn, cursor, statement, parameters, context, executemany):
        if re.search(r"ALTER\s+(?:COLUMN\s+)?role\s+DROP\s+DEFAULT", statement, re.I):
            default_alters.append(True)

    event.listen(connection, "before_cursor_execute", record_default_change)
    try:
        run_migration(connection, identity_migration(), "upgrade")
    finally:
        event.remove(connection, "before_cursor_execute", record_default_change)
    assert len(default_alters) == int(has_server_default)
    assert next(c for c in inspect(connection).get_columns("users", schema=schema)
                if c["name"] == "role")["default"] is None
