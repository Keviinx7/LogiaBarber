"""initial persistence tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("role IN ('admin', 'barber')", name="ck_users_role"), sa.UniqueConstraint("email"))
    op.create_table("services", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text()), sa.Column("price", sa.Numeric(10, 2), nullable=False), sa.Column("duration_minutes", sa.Integer(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("price >= 0", name="ck_services_price_non_negative"), sa.CheckConstraint("duration_minutes > 0", name="ck_services_duration_positive"))
    op.create_table("appointments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_name", sa.String(120), nullable=False), sa.Column("client_phone", sa.String(40), nullable=False), sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id", ondelete="RESTRICT"), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("ends_at > starts_at", name="ck_appointments_time_order"), sa.CheckConstraint("status IN ('pending', 'confirmed', 'completed', 'cancelled', 'no_show')", name="ck_appointments_status"))
    op.create_table("business_hours", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("day_of_week", sa.Integer(), nullable=False), sa.Column("opening_time", sa.Time()), sa.Column("closing_time", sa.Time()), sa.Column("is_open", sa.Boolean(), nullable=False), sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_business_hours_day"), sa.CheckConstraint("NOT is_open OR (opening_time IS NOT NULL AND closing_time IS NOT NULL AND closing_time > opening_time)", name="ck_business_hours_time_order"))
    op.create_table("blocked_times", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reason", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("ends_at > starts_at", name="ck_blocked_times_time_order"))

def downgrade():
    for table in ("blocked_times", "business_hours", "appointments", "services", "users"):
        op.drop_table(table)
