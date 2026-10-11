# Pruebas P0 — Sistema de Gestión para Logia Barber

Empresa: **Logia Barber**. La futura validación PostgreSQL requiere autorización
expresa antes de ejecutar el runner. La normalización de nombres no ejecuta
migraciones, no crea bases y no altera la conexión habitual del proyecto.

Run from `backend/` using the existing virtual environment. No SQLite is used.

Offline checks (no database connection):

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_p0_unit.py
```

Real PostgreSQL checks require exactly `logia_barber_p0_test`. Both the URL and
`SELECT current_database()` must match that name. Every physical migration and
fixture connection is checked before writes; other names are rejected, including
other names containing `test`. There is no fallback to the application's DB.

## A) Preparación inicial: base inexistente

After explicit authorization, the original first-time workflow is:

```sh
.venv/bin/python -B -m tests.run_p0_validation
```

The runner reads the normal connection privately, refuses to continue if its
database is the test target, and checks whether the target exists. An existing
target causes an immediate stop without migration, deletion or tests. If absent,
it creates **only** `logia_barber_p0_test`, verifies it is empty and invokes the
Alembic CLI (`alembic upgrade head`) with a guard on every physical connection.
It verifies the resulting revision, exclusion and extension before running the
PostgreSQL suite followed by the whole suite. The role must have permission to
create this database; insufficient privilege stops execution, without attempting
role changes or creating another database.

This original mode is unchanged: an existing database is always rejected.
It never switches silently to reuse. The current role `logia_barber_app` has no
`CREATEDB`; keep it that way and use mode B for the existing test database.

## B) Regresión: base existente, `--reuse-existing`

Set `P0_TEST_DATABASE_URL` privately to a `postgresql+psycopg` URL for exactly
`logia_barber_p0_test`, using the existing `logia_barber_app` credentials. Do not
put credentials in source control or reports. From `backend/`, run:

```sh
.venv/bin/python -B -m tests.run_p0_validation --reuse-existing
```

The URL is required explicitly; there is no fallback to the normal connection.
The configured test name must be exactly `logia_barber_p0_test`, different from
the application's configured database. Every physical connection retains the
`SELECT current_database()` guard. Similar names such as `logia_barber_test`,
`logia_barber_p0_test_extra`, `postgres`, and `logia_barber` are rejected.

Before enabling pytest, reuse connects only to the test database with
`default_transaction_read_only=on` and confirms the transaction is read-only.
It checks all of the following:

- Exactly one Alembic revision: `0004_identity_persistence`.
- `btree_gist` is installed, without requiring a particular extension version.
- The sole exclusion is `ex_appointments_active_barber_time_overlap`, with
  `barber_id WITH =`, `tstzrange(starts_at, ends_at, '[)') WITH &&`, and only
  `pending`/`confirmed` in the predicate. The complete PostgreSQL definition
  emitted by the existing migration is checked; unexpected definitions fail.
- `ex_appointments_active_time_overlap` is absent, regardless of constraint type.
- `appointments.barber_id` exists and is `NOT NULL`.
- P2.2: exact role constraint without server default, nullable identity links,
  restrictive foreign keys, required uniqueness, and the hash-only session
  table with timezone-aware timestamps. Missing structures fail closed.

A missing/inaccessible database, failed query, or failed check stops execution
before tests. Reuse never creates, drops, repairs, migrates, or seeds a database,
and never changes roles or grants/revokes privileges. It does not require
`CREATEDB`. It performs no `normal_snapshot` or other connection/operation on
the main database `logia_barber`.

Only after the entire preflight passes, child pytest processes receive
`P0_TEST_DATABASE_URL`, `P0_TEST_PREPARED=1`, and `PYTHONDONTWRITEBYTECODE=1`.
The PostgreSQL P0 suite runs first, then P2.2 persistence/migration tests, followed
by the complete suite; any failed suite stops the runner. Fixtures write and clean up only their own test
rows in the guarded test database; the preflight itself is read-only.

**Do not manually run `export P0_TEST_PREPARED=1`.** This bypasses the runner's
protected inspection. The flag is temporary child-process state, not a durable
certificate: neither mode saves it to `.env`, files, the parent shell, or
PostgreSQL. A previous successful run or JSON report does not prepare a new
shell. Always use `--reuse-existing` for a new regression on an existing target.

## Reports and local infrastructure checks

The runner changes connection settings only in process memory, never `.env`.
P0 fixtures do not run migrations or automatically clear an existing schema.
P2.2 migration tests use isolated schemas within the guarded test database and
roll back their outer transaction; they never downgrade public tables. See
[P2.2.md](P2.2.md) for the separate explicit test-database migration command.
Never print connection URLs. Results are recorded, without connection secrets,
in `tests/p0_validation_results.json`.

Existing result files are historical evidence: their observed database names
and paths are preserved, even after a branding change. They do not authorize a
new execution or establish the current test target. Future reports identify
Logia Barber and use paths relative to the project root.

To run all tests locally without preparing PostgreSQL:

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests
```

Without `P0_TEST_DATABASE_URL`, PostgreSQL cases are explicitly skipped. A
configured but wrong/inaccessible/unprepared target fails before fixture writes.
`tests/test_p0_guards.py` checks rejection of wrong configured and actual names.

Fixtures create their own services, barbers, hours, and appointments and delete
only those test rows afterwards. The migrated schema is retained for inspection.
The original mode refuses subsequent runs once this database exists. Use the
explicit reuse mode to inspect it again and run a regression without erasing it.

Runner/guard tests use mocks for all database connections and pytest subprocesses,
including negative schema cases and the original creation workflow. They can be
run without PostgreSQL or `CREATEDB`:

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_p0_guards.py tests/test_p0_runner.py
```

They verify rejection paths, read-only preflight, no migrations/creation/deletion
or main-database access in reuse, temporary preparation only after all checks,
and preservation of the original initial-preparation behavior.

Coverage includes every pair of active statuses, partial overlap in both
directions, containment in both directions, identical/adjacent intervals,
inactive statuses in either insertion order, and separate barbers. Concurrent
HTTP cases synchronize two independent sessions before the barber lock. For
different barbers, a second barrier requires both row locks to be held at once.
Each concurrent scenario runs three times and verifies persisted row counts.
A later valid request reuses the same session after a 409 to verify rollback.

The P0 offline migration tests compile the upgrade through 0003 and only the 0003-to-0002
downgrade, which avoids the out-of-scope downgrade of 0002. Alembic 1.20.0 needs
named exclusion expressions here (`column`/`literal_column`); using `text()`
causes `ArgumentError: Column must be constructed with a non-blank name`.
`drop_constraint` omits `type_` because its supported types exclude `exclude`.
Both operations use Alembic APIs; no explicit DDL fallback was needed.
Migration 0004 requires online inspection and is tested separately; an offline
SQL export cannot inspect an existing role default or downgrade compatibility.
