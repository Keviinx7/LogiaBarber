"""Runner infrastructure tests. All database and subprocess access is mocked."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path
import json
import os

import pytest

from tests import p0_database as guards
from tests import run_p0_validation as runner

TEST_URL = "postgresql+psycopg://logia_barber_app:private@localhost/logia_barber_p0_test"
NORMAL_URL = "postgresql+psycopg://logia_barber_app:private@localhost/logia_barber"
DEFINITION = (
    "EXCLUDE USING gist (barber_id WITH =, tstzrange(starts_at, ends_at, '[)'::text) WITH &&) "
    "WHERE (((status)::text = ANY ((ARRAY['pending'::character varying, "
    "'confirmed'::character varying])::text[])))"
)
CANONICAL = dict(conname=guards.CONSTRAINT, contype="x", definition=DEFINITION)


def simulated_pytest(callback):
    """A mocked child also produces pytest's structured result artifact."""
    def run(args, **kwargs):
        xml_path = Path(args[args.index("--junitxml") + 1])
        xml_path.write_text('<testsuites><testsuite><testcase name="synthetic-pass"/></testsuite></testsuites>')
        return callback(args, **kwargs)
    return run


@pytest.fixture
def reuse(monkeypatch):
    monkeypatch.setenv("P0_TEST_DATABASE_URL", TEST_URL)
    monkeypatch.delenv("P0_TEST_PREPARED", raising=False)
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    monkeypatch.setattr(runner.settings, "database_url", NORMAL_URL)
    state = SimpleNamespace(
        actual=guards.TARGET, readonly="on", revisions=[guards.HEAD],
        extension="1.8", constraints=[deepcopy(CANONICAL)], not_null=True,
        sql=[], report={},
    )
    connection = MagicMock()

    def scalar(statement):
        sql = " ".join(str(statement).split())
        state.sql.append(sql)
        if sql == "SELECT current_database()":
            return state.actual
        if sql == "SHOW transaction_read_only":
            return state.readonly
        if "FROM pg_extension" in sql:
            return state.extension
        if "FROM pg_attribute" in sql:
            return state.not_null
        raise AssertionError(f"Unexpected SQL: {sql}")

    def scalars(statement):
        sql = str(statement)
        state.sql.append(sql)
        assert sql == "SELECT version_num FROM public.alembic_version"
        return state.revisions

    def execute(statement):
        sql = " ".join(str(statement).split())
        state.sql.append(sql)
        assert sql.startswith("SELECT conname, contype, pg_get_constraintdef(oid)")
        return SimpleNamespace(mappings=lambda: state.constraints)

    connection.scalar.side_effect = scalar
    connection.scalars.side_effect = scalars
    connection.execute.side_effect = execute
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    state.engine = engine
    state.factory = MagicMock(return_value=engine)
    monkeypatch.setattr(runner, "guarded_engine", state.factory)
    state.migrate = MagicMock(side_effect=AssertionError("No migrations in reuse"))
    state.connect = MagicMock(side_effect=AssertionError("No unguarded DB connections"))
    state.snapshot = MagicMock(side_effect=AssertionError("No main DB snapshots in reuse"))
    monkeypatch.setattr(runner, "alembic_main", state.migrate)
    monkeypatch.setattr(runner.psycopg, "connect", state.connect)
    monkeypatch.setattr(runner, "normal_snapshot", state.snapshot)
    state.identity = MagicMock(return_value={"verified": True})
    monkeypatch.setattr(guards, "inspect_identity_schema", state.identity)

    def child(args, **kwargs):
        # Inspect the real helper's environment at the exact launch boundary.
        assert state.report["preflight"]["result"] == "PASS"
        assert "FROM pg_attribute" in state.sql[-1]
        state.engine.dispose.assert_called_once_with()
        assert kwargs["env"]["P0_TEST_DATABASE_URL"] == TEST_URL
        assert kwargs["env"]["P0_TEST_PREPARED"] == "1"
        assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert "P0_TEST_PREPARED" not in os.environ
        return SimpleNamespace(returncode=0, stdout="passed\n", stderr="")

    state.children = MagicMock(side_effect=child)
    monkeypatch.setattr(runner.subprocess, "run", simulated_pytest(state.children))
    yield state
    state.migrate.assert_not_called()
    state.connect.assert_not_called()
    state.snapshot.assert_not_called()
    assert all(sql.startswith(("SELECT ", "SHOW ")) for sql in state.sql)
    assert "P0_TEST_PREPARED" not in os.environ
    assert "PYTHONDONTWRITEBYTECODE" not in os.environ
    assert runner.settings.database_url == NORMAL_URL


def reject(state, match):
    with pytest.raises(ValueError, match=match):
        runner.run_reuse_existing(state.report)
    state.children.assert_not_called()
    assert "preflight" not in state.report


def test_reuse_requires_explicit_test_url(reuse, monkeypatch):
    monkeypatch.delenv("P0_TEST_DATABASE_URL")
    reject(reuse, "requires P0_TEST_DATABASE_URL")
    reuse.factory.assert_not_called()


@pytest.mark.parametrize("name", ["logia_barber_p0_test_extra", "logia_barber_test", "postgres", "logia_barber"])
def test_reuse_rejects_wrong_name(reuse, monkeypatch, name):
    monkeypatch.setenv("P0_TEST_DATABASE_URL", f"postgresql+psycopg:///{name}")
    reject(reuse, "exactly logia_barber_p0_test")
    reuse.factory.assert_not_called()


def test_reuse_rejects_wrong_driver(reuse, monkeypatch):
    monkeypatch.setenv("P0_TEST_DATABASE_URL", "sqlite:///logia_barber_p0_test")
    reject(reuse, "exactly logia_barber_p0_test")
    reuse.factory.assert_not_called()


def test_reuse_rejects_application_configured_as_target(reuse, monkeypatch):
    # Restore within this test so the shared fixture can also assert invariance.
    with monkeypatch.context() as patch:
        patch.setattr(runner.settings, "database_url", TEST_URL)
        reject(reuse, "project database is the test target")
    reuse.factory.assert_not_called()


@pytest.mark.parametrize("actual", ["logia_barber", "postgres", "logia_barber_p0_test_extra"])
def test_reuse_rejects_configured_and_actual_database_mismatch(reuse, actual):
    reuse.actual = actual
    reject(reuse, "Actual database")
    assert reuse.sql == ["SELECT current_database()"]
    reuse.engine.dispose.assert_called_once_with()


def test_reuse_missing_database_stops_without_creation(reuse):
    reuse.engine.connect.side_effect = runner.psycopg.OperationalError("database does not exist")
    with pytest.raises(runner.psycopg.OperationalError):
        runner.run_reuse_existing(reuse.report)
    reuse.children.assert_not_called()
    reuse.engine.dispose.assert_called_once_with()
    assert reuse.sql == []


@pytest.mark.parametrize("revisions", [[], ["0002_overlap_constraint"],
    ["0003_barbers_and_schedules"], ["0005_future"], [guards.HEAD, "unexpected_branch"]])
def test_reuse_rejects_incorrect_revision(reuse, revisions):
    reuse.revisions = revisions
    reject(reuse, "Alembic revision")


def test_reuse_rejects_read_write_inspection(reuse):
    reuse.readonly = "off"
    reject(reuse, "read-only transaction")


def test_reuse_rejects_missing_extension(reuse):
    reuse.extension = None
    reject(reuse, "btree_gist")


@pytest.mark.parametrize("constraints", [[], [{**CANONICAL, "contype": "c"}], [{**CANONICAL, "conname": "other_exclusion"}]])
def test_reuse_rejects_missing_canonical_exclusion(reuse, constraints):
    reuse.constraints = constraints
    reject(reuse, "Canonical P0 exclusion")


def test_reuse_rejects_old_constraint_even_with_canonical_present(reuse):
    reuse.constraints.append({**CANONICAL, "conname": guards.OLD_CONSTRAINT})
    reject(reuse, "Legacy")


@pytest.mark.parametrize("definition", [
    DEFINITION.replace("barber_id WITH =", "service_id WITH ="),
    DEFINITION.replace("WITH &&", "WITH ="),
    DEFINITION.replace("'[)'", "'[]'"),
    DEFINITION.replace("tstzrange(starts_at, ends_at", "tstzrange(ends_at, starts_at"),
    DEFINITION.replace("'confirmed'", "'cancelled'"),
    DEFINITION.replace("'confirmed'", "'pending'"),
    DEFINITION.replace("'confirmed'::character varying", "'confirmed'::character varying, 'cancelled'::character varying"),
    DEFINITION + " OR true",
    DEFINITION.split(" WHERE ")[0],
])
def test_reuse_rejects_incorrect_exclusion_semantics(reuse, definition):
    reuse.constraints[0]["definition"] = definition
    reject(reuse, "definition or active-status predicate")


@pytest.mark.parametrize("not_null", [False, None])
def test_reuse_rejects_nullable_or_missing_barber_id(reuse, not_null):
    reuse.not_null = not_null
    reject(reuse, "must exist and be NOT NULL")


@pytest.mark.parametrize("extension", ["1.7", "1.8", "9.9"])
def test_reuse_runs_both_suites_only_after_full_preflight(reuse, extension):
    reuse.extension = extension
    runner.run_reuse_existing(reuse.report)
    reuse.factory.assert_called_once_with(TEST_URL, readonly=True)
    assert [call.args[0][-1] for call in reuse.children.call_args_list] == ["tests/test_p0_postgresql.py", "tests/test_p22_migration.py", "tests"]
    reuse.identity.assert_called_once()
    assert reuse.report["preflight"]["btree_gist"] == extension
    assert "P0_TEST_PREPARED" not in json.dumps(reuse.report)
    assert "private" not in json.dumps(reuse.report)
    # No privilege introspection or escalation: a connection with ordinary
    # catalog-read and fixture DML rights is sufficient; CREATEDB is never used.
    assert all("rolcreatedb" not in sql and "pg_roles" not in sql for sql in reuse.sql)


def test_external_prepared_flag_does_not_bypass_preflight(reuse, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("P0_TEST_PREPARED", "1")
        reuse.not_null = False
        reject(reuse, "must exist and be NOT NULL")
        assert os.environ["P0_TEST_PREPARED"] == "1"


def test_reuse_stops_when_postgresql_suite_fails(reuse):
    reuse.children.side_effect = None
    reuse.children.return_value = SimpleNamespace(returncode=1, stdout="failed", stderr="")
    with pytest.raises(ValueError, match="test run failed"):
        runner.run_reuse_existing(reuse.report)
    reuse.children.assert_called_once()
    assert reuse.children.call_args.args[0][-1] == "tests/test_p0_postgresql.py"


def test_cli_reuse_dispatches_and_records_without_persisting_prepared(reuse, monkeypatch, tmp_path):
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(runner, "REPORT", report_path)
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--reuse-existing"])
    reuse.children.side_effect = None
    reuse.children.return_value = SimpleNamespace(returncode=0, stdout="passed", stderr="")
    assert runner.main() == 0
    report = json.loads(report_path.read_text())
    assert report["mode"] == "reuse-existing"
    assert report["preflight"]["result"] == "PASS"
    assert len(report["test_runs"]) == 3
    assert "P0_TEST_PREPARED" not in report_path.read_text()
    assert "private" not in report_path.read_text()


def test_cli_preflight_failure_never_launches_pytest(reuse, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--reuse-existing"])
    reuse.not_null = False
    assert runner.main() == 1
    reuse.children.assert_not_called()


@pytest.fixture
def initial(monkeypatch):
    monkeypatch.setattr(runner.settings, "database_url", NORMAL_URL)
    snapshot = MagicMock(return_value={"database": "logia_barber"})
    connect = MagicMock()
    cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    factory = MagicMock()
    migrate = MagicMock()
    children = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="passed", stderr=""))
    listen, remove = MagicMock(), MagicMock()
    for name, value in [("normal_snapshot", snapshot), ("guarded_engine", factory), ("alembic_main", migrate)]:
        monkeypatch.setattr(runner, name, value)
    monkeypatch.setattr(runner.psycopg, "connect", connect)
    monkeypatch.setattr(runner.subprocess, "run", simulated_pytest(children))
    monkeypatch.setattr(runner.event, "listen", listen)
    monkeypatch.setattr(runner.event, "remove", remove)
    return SimpleNamespace(snapshot=snapshot, connect=connect, cursor=cursor, factory=factory,
                           migrate=migrate, children=children, listen=listen, remove=remove)


def test_original_mode_still_rejects_existing_database(initial):
    initial.cursor.fetchone.return_value = (True,)
    with pytest.raises(ValueError, match="already exists"):
        runner.run({})
    initial.factory.assert_not_called()
    initial.migrate.assert_not_called()
    initial.children.assert_not_called()
    initial.connect.assert_called_once()
    assert initial.connect.call_args.kwargs["dbname"] == "logia_barber"
    assert "default_transaction_read_only=on" in initial.connect.call_args.kwargs["options"]
    assert initial.cursor.execute.call_count == 1
    assert initial.cursor.execute.call_args.args[0].startswith("SELECT EXISTS")


def test_original_initial_creation_migration_guards_and_suites_are_preserved(initial):
    initial.cursor.fetchone.return_value = (False,)
    connection = initial.factory.return_value.connect.return_value.__enter__.return_value
    connection.scalar.return_value = 0

    def migration(*, argv):
        assert argv == ["upgrade", "head"]
        assert runner.settings.database_url == TEST_URL
        initial.listen.assert_called_once_with(runner.Engine, "connect", guards.require_target_connection)
        initial.children.assert_not_called()

    initial.migrate.side_effect = migration
    report = {}
    from unittest.mock import patch
    with patch.object(runner, "inspect_existing_schema", return_value={"revision": guards.HEAD}) as inspect_schema:
        runner.run(report)
        inspect_schema.assert_called_once_with(connection)
    assert initial.cursor.execute.call_args_list[1].args == ("CREATE DATABASE logia_barber_p0_test",)
    assert initial.connect.call_args_list[1].kwargs["autocommit"] is True
    assert [call.kwargs for call in initial.factory.call_args_list] == [{}, {"readonly": True}]
    assert all(call.args == (TEST_URL,) for call in initial.factory.call_args_list)
    initial.migrate.assert_called_once_with(argv=["upgrade", "head"])
    initial.remove.assert_called_once_with(runner.Engine, "connect", guards.require_target_connection)
    assert runner.settings.database_url == NORMAL_URL
    assert initial.snapshot.call_count == 2
    assert report["normal_snapshot_unchanged"] is True
    assert [call.args[0][-1] for call in initial.children.call_args_list] == ["tests/test_p0_postgresql.py", "tests/test_p22_migration.py", "tests"]
    for call in initial.children.call_args_list:
        assert call.kwargs["env"]["P0_TEST_PREPARED"] == "1"
        assert call.kwargs["env"]["P0_TEST_DATABASE_URL"] == TEST_URL


def test_cli_without_flag_keeps_original_dispatch(initial, monkeypatch, tmp_path):
    monkeypatch.setattr(runner.sys, "argv", ["runner"])
    monkeypatch.setattr(runner, "REPORT", tmp_path / "report.json")
    initial.cursor.fetchone.return_value = (True,)
    reuse = MagicMock(side_effect=AssertionError("Original mode must not reuse"))
    monkeypatch.setattr(runner, "run_reuse_existing", reuse)
    assert runner.main() == 1
    reuse.assert_not_called()
    initial.children.assert_not_called()
