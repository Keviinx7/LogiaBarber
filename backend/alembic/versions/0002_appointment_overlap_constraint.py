"""protect active appointments from concurrent overlaps"""
from alembic import op

revision = "0002_overlap_constraint"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""ALTER TABLE appointments ADD CONSTRAINT ex_appointments_active_time_overlap EXCLUDE USING gist (tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('pending', 'confirmed'))""")


def downgrade():
    op.drop_constraint("ex_appointments_active_time_overlap", "appointments", type_="exclude")
