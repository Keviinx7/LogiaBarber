"""Explicit, guarded 0003 -> 0004 migration of the existing test database only.

This command is separate from run_p0_validation --reuse-existing, which never
migrates. It neither connects to the project database nor creates/seeds a DB.
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os

from alembic.config import main as alembic_main
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url

from app.core.config import settings
from tests.p0_database import (
    HEAD, TARGET, inspect_existing_schema, require_target_connection,
    require_target_url, test_engine as guarded_engine,
)

PREVIOUS = "0003_barbers_and_schedules"


def migrate_existing_test_database():
    raw = os.environ.get("P0_TEST_DATABASE_URL")
    if not raw:
        raise ValueError("P0_TEST_DATABASE_URL is required")
    target = require_target_url(raw)
    if target.database == make_url(settings.database_url).database:
        raise ValueError("Project and test database must be separate")
    engine = guarded_engine(raw, readonly=True)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TARGET:
                raise ValueError("Unexpected actual database")
            revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
            if revisions == [HEAD]:
                inspect_existing_schema(connection)
                print("Test database already at the exact P2.2 head; no migration")
                return
            if revisions != [PREVIOUS]:
                raise ValueError("Expected exactly 0003 before P2.2 migration")
    finally:
        engine.dispose()

    previous_url = settings.database_url
    event.listen(Engine, "connect", require_target_connection)
    try:
        settings.database_url = raw
        # Capture Alembic output; never print driver exceptions or connection URLs.
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            alembic_main(argv=["upgrade", HEAD])
    finally:
        settings.database_url = previous_url
        event.remove(Engine, "connect", require_target_connection)
    engine = guarded_engine(raw, readonly=True)
    try:
        with engine.connect() as connection:
            inspect_existing_schema(connection)
    finally:
        engine.dispose()
    print("P2.2 migration and full preflight: PASS on", TARGET)


def main():
    try:
        migrate_existing_test_database()
    except Exception as error:
        print("STOP: test migration/preflight failed; details hidden:", type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
