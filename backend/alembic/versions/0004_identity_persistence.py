"""Add identity links and hashed server-side session persistence."""

from alembic import op
import sqlalchemy as sa


revision = "0004_identity_persistence"
down_revision = "0003_barbers_and_schedules"
branch_labels = None
depends_on = None


def _online_connection():
    # Defaults and downgrade compatibility must be checked against real data.
    if op.get_context().as_sql:
        raise RuntimeError("Identity migration requires online schema inspection")
    return op.get_bind()


def upgrade():
    connection = _online_connection()
    role_column = next(
        column for column in sa.inspect(connection).get_columns("users")
        if column["name"] == "role"
    )
    if role_column["default"] is not None:
        op.alter_column("users", "role", server_default=None)

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('owner', 'admin', 'barber', 'client')"
    )

    op.add_column("barbers", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_barbers_user_id", "barbers", "users", ["user_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_barbers_user_id", "barbers", ["user_id"])

    op.add_column("appointments", sa.Column("client_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_client_user_id", "appointments", "users",
        ["client_user_id"], ["id"], ondelete="RESTRICT",
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_sessions_user_id", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("session_token_hash", name="uq_auth_sessions_session_token_hash"),
    )
    # Enables user-scoped session lookup without scanning every session.
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade():
    connection = _online_connection()
    # Prevent a concurrent new role from appearing after the pre-DDL check.
    connection.execute(sa.text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    incompatible_users = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM users WHERE role NOT IN ('admin', 'barber'))"
    )).scalar_one()
    if incompatible_users:
        raise RuntimeError(
            "Cannot downgrade identity persistence while users have roles incompatible with 0003"
        )

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_constraint("fk_appointments_client_user_id", "appointments", type_="foreignkey")
    op.drop_column("appointments", "client_user_id")
    op.drop_constraint("uq_barbers_user_id", "barbers", type_="unique")
    op.drop_constraint("fk_barbers_user_id", "barbers", type_="foreignkey")
    op.drop_column("barbers", "user_id")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('admin', 'barber')")
