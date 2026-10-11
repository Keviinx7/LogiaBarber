"""P2.2 catalog rejection and explicit test migration; all I/O is mocked."""
from copy import deepcopy
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

from tests import p0_database as guards
from tests import migrate_p22_test_database as migration
from tests import run_p0_validation as runner
from tests.test_p0_runner import reuse  # noqa: F401 -- shared guarded-runner fixture


ROLE_FORMS = (
    "role::text = ANY (ARRAY[{values}]::text[])",
    "(role)::text = ANY ((ARRAY[{values}])::text[])",
)
ROLES = ("owner", "admin", "barber", "client")


def role_expression(form, roles=ROLES):
    return form.format(values=", ".join(f"'{role}'::character varying" for role in roles))


@pytest.fixture
def catalog(monkeypatch):
    def col(name, kind, nullable=False):
        return {"name": name, "type": kind, "nullable": nullable, "default": None}

    columns = {
        "users": [col("role", sa.String(20))],
        "barbers": [col("user_id", sa.Integer(), True)],
        "appointments": [col("client_user_id", sa.Integer(), True)],
        "auth_sessions": [col("id", sa.Integer()), col("user_id", sa.Integer()),
            col("session_token_hash", sa.String(64)), col("csrf_token_hash", sa.String(64)),
            col("created_at", sa.TIMESTAMP(timezone=True)),
            col("expires_at", sa.TIMESTAMP(timezone=True)),
            col("revoked_at", sa.TIMESTAMP(timezone=True), True)],
    }
    roles = "(role)::text = ANY ((ARRAY['owner'::character varying, 'admin'::character varying, 'barber'::character varying, 'client'::character varying])::text[])"
    checks = [{"name": "ck_users_role", "sqltext": roles}]
    fks = {table: [{"constrained_columns": [name], "referred_table": "users",
                    "referred_columns": ["id"], "referred_schema": "public",
                    "options": {"ondelete": "RESTRICT"}}]
           for table, name in (("barbers", "user_id"), ("appointments", "client_user_id"),
                               ("auth_sessions", "user_id"))}
    uniques = {"barbers": [{"column_names": ["user_id"]}],
               "auth_sessions": [{"column_names": ["session_token_hash"]}]}
    inspector = MagicMock()
    inspector.get_table_names.side_effect = lambda **kw: list(columns)
    inspector.get_columns.side_effect = lambda table, **kw: columns[table]
    inspector.get_check_constraints.return_value = checks
    inspector.get_foreign_keys.side_effect = lambda table, **kw: fks[table]
    inspector.get_unique_constraints.side_effect = lambda table, **kw: uniques[table]
    inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    monkeypatch.setattr(guards, "inspect", lambda connection: inspector)
    return SimpleNamespace(columns=columns, checks=checks, fks=fks, uniques=uniques, inspector=inspector)


def test_complete_identity_catalog_accepted(catalog):
    assert guards.inspect_identity_schema(object())["session_hashes_only"] is True


@pytest.mark.parametrize("form", ROLE_FORMS, ids=["observed", "redundant-parentheses"])
@pytest.mark.parametrize("roles", list(permutations(ROLES)))
def test_canonical_role_forms_accept_exact_roles_in_any_order(catalog, form, roles):
    catalog.checks[0]["sqltext"] = role_expression(form, roles)
    assert guards.inspect_identity_schema(object())["roles"] == list(ROLES)


@pytest.mark.parametrize("table", ["users", "barbers", "appointments", "auth_sessions"])
def test_missing_table_rejected(catalog, table):
    del catalog.columns[table]
    with pytest.raises(ValueError, match="table is absent"):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("table,name", [("barbers", "user_id"), ("appointments", "client_user_id"),
    ("auth_sessions", "csrf_token_hash"), ("auth_sessions", "expires_at")])
def test_missing_identity_column_rejected(catalog, table, name):
    catalog.columns[table] = [c for c in catalog.columns[table] if c["name"] != name]
    with pytest.raises(ValueError):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("table", ["barbers", "appointments", "auth_sessions"])
def test_missing_fk_rejected(catalog, table):
    catalog.fks[table] = []
    with pytest.raises(ValueError, match="FK"):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("table", ["barbers", "auth_sessions"])
def test_missing_unique_rejected(catalog, table):
    catalog.uniques[table] = []
    with pytest.raises(ValueError, match="UNIQUE"):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("form", ROLE_FORMS, ids=["observed", "redundant-parentheses"])
@pytest.mark.parametrize("change", [
    "extra", "extra-duplicate", "duplicate", "missing", "other-role", "or_true",
    "prefix", "partial", "different-column", "different-operator", "all",
    "different-cast", "unbalanced", "comment", "different-expression",
])
def test_inexact_role_predicate_rejected(catalog, form, change):
    original = role_expression(form)
    catalog.checks[0]["sqltext"] = {
        "extra": original.replace("'client'::character varying", "'client'::character varying, 'root'::character varying"),
        "extra-duplicate": original.replace("'client'::character varying", "'client'::character varying, 'client'::character varying"),
        "duplicate": original.replace("'client'", "'admin'"),
        "missing": original.replace("'owner'::character varying, ", ""),
        "other-role": original.replace("'client'", "'root'"),
        "or_true": original + " OR true",
        "prefix": "true OR " + original,
        "partial": original[:-1],
        "different-column": original.replace("role", "name", 1),
        "different-operator": original.replace(" = ANY", " <> ANY"),
        "all": original.replace("ANY", "ALL"),
        "different-cast": original.replace("::text[]", "::integer[]"),
        "unbalanced": "(" + original,
        "comment": original + " -- ignored suffix",
        "different-expression": "role IN ('owner', 'admin', 'barber', 'client') OR role IS NULL",
    }[change]
    with pytest.raises(ValueError, match="allowed roles"):
        guards.inspect_identity_schema(object())


def test_different_role_constraint_name_rejected(catalog):
    catalog.checks[0]["name"] = "another_role_check"
    with pytest.raises(ValueError, match="role constraint is absent"):
        guards.inspect_identity_schema(object())


def test_role_server_default_rejected(catalog):
    catalog.columns["users"][0]["default"] = "'barber'::character varying"
    with pytest.raises(ValueError, match="server default"):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("table", ["barbers", "appointments"])
def test_historical_links_must_stay_nullable(catalog, table):
    catalog.columns[table][0]["nullable"] = False
    with pytest.raises(ValueError, match="column"):
        guards.inspect_identity_schema(object())


@pytest.mark.parametrize("options", [{"ondelete": "CASCADE"}, {"ondelete": "SET NULL"}])
def test_destructive_or_identity_losing_fk_rejected(catalog, options):
    catalog.fks["barbers"][0]["options"] = options
    with pytest.raises(ValueError, match="delete policy"):
        guards.inspect_identity_schema(object())


def test_wrong_fk_target_rejected(catalog):
    catalog.fks["appointments"][0]["referred_table"] = "barbers"
    with pytest.raises(ValueError, match="FK target"):
        guards.inspect_identity_schema(object())


def test_raw_session_column_rejected(catalog):
    raw = deepcopy(catalog.columns["auth_sessions"][2])
    raw["name"] = "session_token"
    catalog.columns["auth_sessions"].append(raw)
    with pytest.raises(ValueError, match="raw secrets"):
        guards.inspect_identity_schema(object())


def test_session_timezone_required(catalog):
    catalog.columns["auth_sessions"][-1]["type"] = sa.TIMESTAMP(timezone=False)
    with pytest.raises(ValueError, match="timezone"):
        guards.inspect_identity_schema(object())


def test_identity_preflight_failure_prevents_all_suites(reuse):
    reuse.identity.side_effect = ValueError("P2.2 relationship missing")
    with pytest.raises(ValueError, match="relationship missing"):
        runner.run_reuse_existing(reuse.report)
    reuse.children.assert_not_called()


def test_external_prepared_flag_cannot_skip_identity_preflight(reuse, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("P0_TEST_PREPARED", "1")
        reuse.identity.side_effect = ValueError("auth_sessions absent")
        with pytest.raises(ValueError, match="auth_sessions"):
            runner.run_reuse_existing(reuse.report)
        reuse.children.assert_not_called()


@pytest.mark.parametrize("output", ["38 passed, 1 skipped", "", "s [100%]"])
def test_prepared_run_rejects_skipped_cases_even_with_zero_exit(reuse, output):
    def skipped(args, **kwargs):
        Path(args[args.index("--junitxml") + 1]).write_text(
            '<testsuites><testsuite><testcase name="omitted"><skipped/></testcase></testsuite></testsuites>')
        return SimpleNamespace(returncode=0, stdout=output, stderr="")
    reuse.children.side_effect = skipped
    with pytest.raises(ValueError, match="must not omit"):
        runner.run_reuse_existing(reuse.report)
    reuse.children.assert_called_once()


@pytest.mark.parametrize("xml", ["invalid XML", "<testsuites/>",
    '<testsuites><testcase><failure/></testcase></testsuites>',
    '<testsuites><testcase><error/></testcase></testsuites>'])
def test_prepared_run_rejects_invalid_empty_or_failed_structured_results(reuse, xml):
    def result(args, **kwargs):
        Path(args[args.index("--junitxml") + 1]).write_text(xml)
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")
    reuse.children.side_effect = result
    with pytest.raises((ValueError, runner.ElementTree.ParseError)):
        runner.run_reuse_existing(reuse.report)
    reuse.children.assert_called_once()


def test_prepared_run_removes_inherited_pytest_selection_and_verbosity(reuse, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-qqq -k hide_required_tests")
    runner.run_reuse_existing(reuse.report)
    for call in reuse.children.call_args_list:
        assert "PYTEST_ADDOPTS" not in call.kwargs["env"]
    assert reuse.report["test_runs"][0]["counts"] == {
        "tests": 1, "skipped": 0, "failures": 0, "errors": 0,
    }


@pytest.fixture
def migrate(monkeypatch):
    monkeypatch.setenv("P0_TEST_DATABASE_URL", "postgresql+psycopg:///logia_barber_p0_test")
    monkeypatch.setattr(migration.settings, "database_url", "postgresql+psycopg:///logia_barber")
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = guards.TARGET
    connection.scalars.return_value = [migration.PREVIOUS]
    factory = MagicMock(return_value=engine)
    upgrade, inspect_schema, listen, remove = (MagicMock() for _ in range(4))
    monkeypatch.setattr(migration, "guarded_engine", factory)
    monkeypatch.setattr(migration, "alembic_main", upgrade)
    monkeypatch.setattr(migration, "inspect_existing_schema", inspect_schema)
    monkeypatch.setattr(migration.event, "listen", listen)
    monkeypatch.setattr(migration.event, "remove", remove)
    return SimpleNamespace(connection=connection, factory=factory, upgrade=upgrade,
                           inspect=inspect_schema, listen=listen, remove=remove)


def test_explicit_migration_only_accepts_exact_test_target(migrate, monkeypatch):
    monkeypatch.setenv("P0_TEST_DATABASE_URL", "postgresql+psycopg:///logia_barber")
    with pytest.raises(ValueError):
        migration.migrate_existing_test_database()
    migrate.factory.assert_not_called()
    migrate.upgrade.assert_not_called()


@pytest.mark.parametrize("actual", ["logia_barber", "another_test"])
def test_explicit_migration_checks_actual_database(migrate, actual):
    migrate.connection.scalar.return_value = actual
    with pytest.raises(ValueError):
        migration.migrate_existing_test_database()
    migrate.upgrade.assert_not_called()


@pytest.mark.parametrize("revisions", [[], ["0002_overlap_constraint"], ["0005_future"]])
def test_explicit_migration_rejects_unexpected_source(migrate, revisions):
    migrate.connection.scalars.return_value = revisions
    with pytest.raises(ValueError):
        migration.migrate_existing_test_database()
    migrate.upgrade.assert_not_called()


def test_explicit_migration_uses_physical_guard_and_exact_destination(migrate):
    migration.migrate_existing_test_database()
    migrate.upgrade.assert_called_once_with(argv=["upgrade", "0004_identity_persistence"])
    migrate.listen.assert_called_once_with(migration.Engine, "connect", guards.require_target_connection)
    migrate.remove.assert_called_once_with(migration.Engine, "connect", guards.require_target_connection)
    migrate.inspect.assert_called_once()
    assert migration.settings.database_url == "postgresql+psycopg:///logia_barber"
    assert all(call.kwargs == {"readonly": True} for call in migrate.factory.call_args_list)


def test_explicit_migration_at_head_only_inspects(migrate):
    migrate.connection.scalars.return_value = [guards.HEAD]
    migration.migrate_existing_test_database()
    migrate.upgrade.assert_not_called()
    migrate.inspect.assert_called_once()


def test_explicit_migration_failure_restores_settings_and_hides_details(migrate, capsys):
    migrate.upgrade.side_effect = RuntimeError("driver details must not be exposed")
    assert migration.main() == 1
    assert "driver details" not in capsys.readouterr().out
    assert migration.settings.database_url == "postgresql+psycopg:///logia_barber"
    migrate.remove.assert_called_once()
