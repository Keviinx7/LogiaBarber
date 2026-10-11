"""Add barbers and make schedules independent per barber."""
from alembic import op
import sqlalchemy as sa

revision = "0003_barbers_and_schedules"
down_revision = "0002_overlap_constraint"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("barbers",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("INSERT INTO barbers (name) VALUES ('Barbero 1'), ('Barbero 2')")
    op.add_column("appointments", sa.Column("barber_id", sa.Integer(), nullable=True))
    op.execute("UPDATE appointments SET barber_id = 1 WHERE barber_id IS NULL")
    op.create_foreign_key("fk_appointments_barber_id", "appointments", "barbers", ["barber_id"], ["id"], ondelete="RESTRICT")
    op.alter_column("appointments", "barber_id", nullable=False)
    op.create_index("ix_appointments_barber_id", "appointments", ["barber_id"])
    op.add_column("business_hours", sa.Column("barber_id", sa.Integer(), nullable=True))
    op.execute("UPDATE business_hours SET barber_id = 1 WHERE barber_id IS NULL")
    op.create_foreign_key("fk_business_hours_barber_id", "business_hours", "barbers", ["barber_id"], ["id"], ondelete="CASCADE")
    op.alter_column("business_hours", "barber_id", nullable=False)
    op.create_index("ix_business_hours_barber_id", "business_hours", ["barber_id"])
    op.execute("INSERT INTO business_hours (barber_id, day_of_week, opening_time, closing_time, is_open) SELECT 2, day_of_week, opening_time, closing_time, is_open FROM business_hours WHERE barber_id = 1")
    op.add_column("blocked_times", sa.Column("barber_id", sa.Integer(), nullable=True))
    op.execute("UPDATE blocked_times SET barber_id = 1 WHERE barber_id IS NULL")
    op.create_foreign_key("fk_blocked_times_barber_id", "blocked_times", "barbers", ["barber_id"], ["id"], ondelete="CASCADE")
    op.alter_column("blocked_times", "barber_id", nullable=False)
    op.create_index("ix_blocked_times_barber_id", "blocked_times", ["barber_id"])
    # PostgreSQL needs no type hint; Alembic drop_constraint has no "exclude" type.
    op.drop_constraint("ex_appointments_active_time_overlap", "appointments")
    op.create_exclude_constraint(
        "ex_appointments_active_barber_time_overlap",
        "appointments",
        (sa.column("barber_id"), "="),
        # Alembic requires named expressions here; TextClause has no name.
        (sa.literal_column("tstzrange(starts_at, ends_at, '[)')"), "&&"),
        where=sa.text("status IN ('pending', 'confirmed')"),
        using="gist",
    )

def downgrade():
    op.drop_constraint("ex_appointments_active_barber_time_overlap", "appointments")
    op.create_exclude_constraint(
        "ex_appointments_active_time_overlap",
        "appointments",
        (sa.literal_column("tstzrange(starts_at, ends_at, '[)')"), "&&"),
        where=sa.text("status IN ('pending', 'confirmed')"),
        using="gist",
    )
    op.drop_column("blocked_times", "barber_id"); op.drop_column("business_hours", "barber_id"); op.drop_column("appointments", "barber_id"); op.drop_table("barbers")
