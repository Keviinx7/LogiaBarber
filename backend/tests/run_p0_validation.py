"""Create ONLY the authorized P0 database, migrate, inspect and run both suites.

Run from backend: .venv/bin/python -B -m tests.run_p0_validation
Without --reuse-existing, an existing target causes an immediate stop.
--reuse-existing inspects only the existing target, without creation or migration.
"""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from importlib.metadata import version
from io import StringIO
from pathlib import Path
import json
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import psycopg
from alembic.config import main as alembic_main
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url

from app.core.config import settings
from tests.p0_database import (
    HEAD, TARGET, inspect_existing_schema, require_target_connection,
    require_target_url, test_engine as guarded_engine,
)

BACKEND = Path(__file__).resolve().parents[1]
REPORT = BACKEND / "tests/p0_validation_results.json"


def connect_params(url, *, readonly=True):
    params = url.translate_connect_args(username="user", database="dbname")
    params.update(dict(url.query))
    params.update(connect_timeout=5, options="-c statement_timeout=15000")
    if readonly:
        params["options"] += " -c default_transaction_read_only=on"
    return params


def normal_snapshot(url):
    with psycopg.connect(**connect_params(url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version')")
            name, server_version = cursor.fetchone()
            if name == TARGET:
                raise ValueError("Current project database is the test target; stopped")
            cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
            revisions = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.appointments'::regclass ORDER BY conname")
            constraints = cursor.fetchall()
            cursor.execute("SELECT count(*) FROM appointments")
            count = cursor.fetchone()[0]
    return dict(database=name, postgresql=server_version, revisions=revisions,
                appointment_constraints=constraints, appointment_count=count)


def run_test_suites(report, raw_target):
    # The application .env stays unchanged. Only the child test processes
    # receive the private test URL; every fixture connection is guarded too.
    env = dict(os.environ, P0_TEST_DATABASE_URL=raw_target,
               P0_TEST_PREPARED="1", PYTHONDONTWRITEBYTECODE="1")
    # A prepared regression must not inherit selection/formatting overrides.
    env.pop("PYTEST_ADDOPTS", None)
    report["test_runs"] = []
    for targets in (("tests/test_p0_postgresql.py",),
                    ("tests/test_p22_postgresql.py", "tests/test_p22_migration.py"),
                    ("tests",)):
        with TemporaryDirectory(prefix="logia-p22-results-") as directory:
            xml_path = Path(directory) / "pytest.xml"
            args = [sys.executable, "-B", "-m", "pytest", "-v", "-s", "--tb=short",
                    "-p", "no:cacheprovider", "--junitxml", str(xml_path), *targets]
            result = subprocess.run(args, cwd=BACKEND, env=env, text=True, capture_output=True, timeout=180)
            if result.returncode == 0:
                # Fail closed on absent/malformed results as well as skips;
                # stdout verbosity can never turn missing cases into a PASS.
                cases = list(ElementTree.parse(xml_path).getroot().iter("testcase"))
                counts = dict(tests=len(cases), skipped=sum(c.find("skipped") is not None for c in cases),
                              failures=sum(c.find("failure") is not None for c in cases),
                              errors=sum(c.find("error") is not None for c in cases))
            else:
                counts = None
        report["test_runs"].append(dict(command=args, database=TARGET, exit_code=result.returncode,
                                        counts=counts, output=result.stdout + result.stderr))
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        if result.returncode:
            raise ValueError("P0 test run failed; retained database for inspection")
        if not counts["tests"] or counts["skipped"] or counts["failures"] or counts["errors"]:
            raise ValueError("Prepared PostgreSQL suites must not omit required tests")


def run(report):
    current_url = make_url(settings.database_url)
    if current_url.database == TARGET:
        raise ValueError("Configured project database is the test target; stopped")
    report["normal_before"] = normal_snapshot(current_url)
    print("Configured database:", current_url.database, flush=True)
    with psycopg.connect(**connect_params(current_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname=%s)", (TARGET,))
            exists = cursor.fetchone()[0]
    report["target_existed_before"] = exists
    if exists:
        raise ValueError("logia_barber_p0_test already exists; stopped without changing it")

    # No IF NOT EXISTS: if another process creates it after preflight, fail.
    with psycopg.connect(**connect_params(current_url, readonly=False), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE logia_barber_p0_test")
    report["created_database"] = TARGET
    print("Created exclusively:", TARGET, flush=True)
    target_url = current_url.set(database=TARGET)
    raw_target = target_url.render_as_string(hide_password=False)
    engine = guarded_engine(raw_target)
    try:
        with engine.connect() as connection:
            relations = connection.scalar(text("""
                SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND n.nspname NOT LIKE 'pg_toast%'
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
            """))
        report["user_relations_before_migration"] = relations
        if relations != 0:
            raise ValueError("New target is not empty; stopped without deleting anything")

        # Invoke the Alembic CLI in-process so EVERY migration connection must
        # prove its real database name before Alembic can issue its first DDL.
        previous_url = settings.database_url
        event.listen(Engine, "connect", require_target_connection)
        output = StringIO()
        try:
            settings.database_url = raw_target
            with redirect_stdout(output), redirect_stderr(output):
                alembic_main(argv=["upgrade", "head"])
        finally:
            settings.database_url = previous_url
            event.remove(Engine, "connect", require_target_connection)
        report["migration"] = dict(command="alembic upgrade head", database=TARGET, result="PASS")
        print("alembic upgrade head: PASS on", TARGET, flush=True)

        inspection_engine = guarded_engine(raw_target, readonly=True)
        try:
            with inspection_engine.connect() as connection:
                report["catalog_after_migration"] = inspect_existing_schema(connection)
        finally:
            inspection_engine.dispose()
        print(json.dumps(report["catalog_after_migration"], ensure_ascii=False), flush=True)

        run_test_suites(report, raw_target)
    finally:
        engine.dispose()
        report["normal_after"] = normal_snapshot(current_url)
        report["normal_snapshot_unchanged"] = report["normal_before"] == report["normal_after"]


def run_reuse_existing(report):
    raw_target = os.environ.get("P0_TEST_DATABASE_URL")
    if not raw_target:
        raise ValueError("--reuse-existing requires P0_TEST_DATABASE_URL")
    target_url = require_target_url(raw_target)
    if target_url.database == make_url(settings.database_url).database:
        raise ValueError("Configured project database is the test target; stopped")

    # No connection to the application's database, even for a snapshot. The
    # existing physical-connection guard runs before all catalog inspection.
    # A missing/inaccessible target fails on connect: never create or repair it.
    engine = guarded_engine(raw_target, readonly=True)
    try:
        with engine.connect() as connection:
            catalog = inspect_existing_schema(connection)
    finally:
        engine.dispose()
    report["preflight"] = dict(database=TARGET, readonly=True, result="PASS", **catalog)
    print("Existing P0 target preflight: PASS on", TARGET, flush=True)
    run_test_suites(report, raw_target)


def main():
    if sys.argv[1:] == ["--inspect"]:
        # Read-only follow-up; never retries creation or runs migrations/tests.
        report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
        url = make_url(settings.database_url)
        report["normal_after"] = normal_snapshot(url)
        with psycopg.connect(**connect_params(url)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname=%s)", (TARGET,))
                report["target_exists_after"] = cursor.fetchone()[0]
        # Normalize tuples through JSON before comparing with a stored snapshot.
        report["normal_snapshot_unchanged"] = report.get("normal_before") == json.loads(json.dumps(report["normal_after"]))
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({key: report[key] for key in ("target_exists_after", "normal_snapshot_unchanged")}))
        return 0
    reuse_existing = sys.argv[1:] == ["--reuse-existing"]
    if sys.argv[1:] and not reuse_existing:
        raise SystemExit("Only --inspect or --reuse-existing is supported; no action performed")
    project_root = BACKEND.parent
    report = dict(project="Sistema de Gestión para Logia Barber", company="Logia Barber",
                  python=sys.version.split()[0],
                  python_executable=os.path.relpath(sys.executable, project_root),
                  alembic=version("alembic"), cwd=os.path.relpath(Path.cwd(), project_root),
                  timestamp_utc=datetime.now(timezone.utc).isoformat())
    try:
        if reuse_existing:
            report["mode"] = "reuse-existing"
            run_reuse_existing(report)
        else:
            run(report)
    except Exception as error:
        # Never include driver messages or connection URLs in the report.
        report["failure"] = dict(type=type(error).__name__, sqlstate=getattr(error, "sqlstate", None))
        print("STOP:", report["failure"], flush=True)
        result = 1
    else:
        result = 0
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
