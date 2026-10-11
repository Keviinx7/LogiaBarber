"""Fail-closed database guards shared by the P0 runner and its fixtures."""
import re

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url

TARGET = "logia_barber_p0_test"
HEAD = "0004_identity_persistence"
CONSTRAINT = "ex_appointments_active_barber_time_overlap"
OLD_CONSTRAINT = "ex_appointments_active_time_overlap"

# Match the complete PostgreSQL definition produced by the existing migration.
# Substring checks for "pending"/"confirmed" would also accept extra statuses
# or an OR true predicate. Unexpected definitions fail closed, without repair.
EXCLUSION_DEFINITION = re.compile(
    r"EXCLUDE USING gist \(barber_id WITH =, "
    r"tstzrange\(starts_at, ends_at, '\[\)'::text\) WITH &&\) "
    r"WHERE \(\(\(status\)::text = ANY \(\(ARRAY\["
    r"'(pending|confirmed)'::character varying, "
    r"'(pending|confirmed)'::character varying\]"
    r"\)::text\[\]\)\)\)"
)


def require_target_url(raw_url):
    url = make_url(raw_url)
    if url.drivername != "postgresql+psycopg" or url.database != TARGET:
        raise ValueError("P0 requires exactly logia_barber_p0_test with psycopg")
    return url


def require_target_connection(dbapi_connection, connection_record=None):
    # Executed for every physical connection, before migration/fixture SQL.
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        actual = cursor.fetchone()[0]
    dbapi_connection.rollback()
    if actual != TARGET:
        raise ValueError("P0 refused connection: actual database is not logia_barber_p0_test")


def test_engine(raw_url, *, readonly=False):
    url = require_target_url(raw_url)
    options = "-c statement_timeout=15000 -c lock_timeout=10000"
    if readonly:
        options += " -c default_transaction_read_only=on"
    engine = create_engine(url, connect_args={
        "connect_timeout": 5,
        "options": options,
    })
    event.listen(engine, "connect", require_target_connection)
    return engine


def inspect_existing_schema(connection):
    """Read and validate the complete P0 preflight before enabling child tests."""
    if connection.scalar(text("SELECT current_database()")) != TARGET:
        raise ValueError("Actual database is not logia_barber_p0_test")
    if connection.scalar(text("SHOW transaction_read_only")) != "on":
        raise ValueError("P0 reuse inspection requires a read-only transaction")
    revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
    if revisions != [HEAD]:
        raise ValueError("Unexpected Alembic revision; no migration performed")
    extension = connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='btree_gist'"))
    if not extension:
        raise ValueError("Required btree_gist extension is absent")
    constraints = [dict(row) for row in connection.execute(text("""
        SELECT conname, contype, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint WHERE conrelid='public.appointments'::regclass
        ORDER BY conname
    """)).mappings()]
    if any(row["conname"] == OLD_CONSTRAINT for row in constraints):
        raise ValueError("Legacy appointment exclusion is still present")
    exclusions = [row for row in constraints if row["contype"] == "x"]
    if len(exclusions) != 1 or exclusions[0]["conname"] != CONSTRAINT:
        raise ValueError("Canonical P0 exclusion is absent or unexpected exclusions exist")
    definition = " ".join(exclusions[0]["definition"].split())
    match = EXCLUSION_DEFINITION.fullmatch(definition)
    if not match or set(match.groups()) != {"pending", "confirmed"}:
        raise ValueError("Unexpected P0 exclusion definition or active-status predicate")
    not_null = connection.scalar(text("""
        SELECT attnotnull FROM pg_attribute
        WHERE attrelid='public.appointments'::regclass
          AND attname='barber_id' AND attnum > 0 AND NOT attisdropped
    """))
    if not_null is not True:
        raise ValueError("appointments.barber_id must exist and be NOT NULL")
    identity = inspect_identity_schema(connection)
    return dict(revision=revisions[0], btree_gist=extension,
                exclusions=exclusions, barber_id_not_null=True, identity=identity)


def inspect_identity_schema(connection):
    """Fail closed on missing or altered P2.2 identity structures (read only)."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names(schema="public"))
    if not {"users", "barbers", "appointments", "auth_sessions"} <= tables:
        raise ValueError("Required P2.2 identity table is absent")
    columns = {
        table: {column["name"]: column for column in inspector.get_columns(table, schema="public")}
        for table in ("users", "barbers", "appointments", "auth_sessions")
    }

    def column(table, name, type_name, nullable):
        actual = columns[table].get(name)
        if actual is None or actual["nullable"] is not nullable or str(actual["type"]) != type_name:
            raise ValueError(f"Unexpected P2.2 column: {table}.{name}")
        return actual

    role = column("users", "role", "VARCHAR(20)", False)
    if role.get("default") is not None:
        raise ValueError("users.role must not have a server default")
    checks = inspector.get_check_constraints("users", schema="public")
    role_checks = [check for check in checks if check["name"] == "ck_users_role"]
    if len(role_checks) != 1:
        raise ValueError("Required P2.2 role constraint is absent")
    # Accept only the observed canonical rendering and the older rendering
    # with redundant parentheses. Keep both grammars explicit and balanced;
    # do not strip arbitrary parentheses or search for role substrings.
    expression = " ".join(role_checks[0]["sqltext"].split())
    values = (
        r"'([a-z]+)'::character varying, '([a-z]+)'::character varying, "
        r"'([a-z]+)'::character varying, '([a-z]+)'::character varying"
    )
    patterns = (
        r"role::text = ANY \(ARRAY\[" + values + r"\]::text\[\]\)",
        r"\(role\)::text = ANY \(\(ARRAY\[" + values + r"\]\)::text\[\]\)",
    )
    match = next((matched for pattern in patterns
                  if (matched := re.fullmatch(pattern, expression))), None)
    # Exactly four captures plus this set comparison reject missing,
    # additional, duplicated or substituted roles, regardless of order.
    if not match or set(match.groups()) != {"owner", "admin", "barber", "client"}:
        raise ValueError("Unexpected P2.2 allowed roles")
    column("barbers", "user_id", "INTEGER", True)
    column("appointments", "client_user_id", "INTEGER", True)
    session_spec = {
        "id": ("INTEGER", False), "user_id": ("INTEGER", False),
        "session_token_hash": ("VARCHAR(64)", False),
        "csrf_token_hash": ("VARCHAR(64)", False),
        "created_at": ("TIMESTAMP", False), "expires_at": ("TIMESTAMP", False),
        "revoked_at": ("TIMESTAMP", True),
    }
    if set(columns["auth_sessions"]) != set(session_spec):
        raise ValueError("Unexpected P2.2 session columns; raw secrets are not allowed")
    for name, (kind, nullable) in session_spec.items():
        actual = column("auth_sessions", name, kind, nullable)
        if kind == "TIMESTAMP" and not actual["type"].timezone:
            raise ValueError("Session timestamps must include timezone")
    if inspector.get_pk_constraint("auth_sessions", schema="public")["constrained_columns"] != ["id"]:
        raise ValueError("Unexpected P2.2 session primary key")
    for table, name in (("barbers", "user_id"), ("appointments", "client_user_id"),
                        ("auth_sessions", "user_id")):
        fks = inspector.get_foreign_keys(table, schema="public")
        candidates = [fk for fk in fks if fk["constrained_columns"] == [name]]
        if len(candidates) != 1:
            raise ValueError(f"Missing or ambiguous P2.2 FK: {table}.{name}")
        fk = candidates[0]
        if (fk["referred_table"] != "users" or fk["referred_columns"] != ["id"]
                or fk.get("referred_schema") not in (None, "public")
                or fk.get("options", {}).get("ondelete") != "RESTRICT"):
            raise ValueError(f"Unexpected P2.2 FK target or delete policy: {table}.{name}")
    for table, name in (("barbers", "user_id"), ("auth_sessions", "session_token_hash")):
        uniques = inspector.get_unique_constraints(table, schema="public")
        if not any(item["column_names"] == [name] for item in uniques):
            raise ValueError(f"Missing P2.2 UNIQUE: {table}.{name}")
    return {"roles": ["owner", "admin", "barber", "client"],
            "nullable_historical_links": True, "session_hashes_only": True,
            "foreign_keys": True, "unique_links_and_session_hash": True}
