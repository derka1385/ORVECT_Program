"""Vehicle generations, engine variants and reported real-world issues.

Revision ID: 0015
Revises: 0014

Reference data only (no tenant data). Idempotent like 0014: tables are created
only when missing, because a fresh database may already carry them from
``Base.metadata``.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TABLES = ("vehicle_generations", "engine_variants", "reported_vehicle_issues", "reported_issue_generations")


def upgrade():
    from app.database.models import Base
    bind = op.get_bind()
    present = set(sa.inspect(bind).get_table_names())
    for name in TABLES:
        if name not in present:
            Base.metadata.tables[name].create(bind)


def downgrade():
    bind = op.get_bind()
    present = set(sa.inspect(bind).get_table_names())
    for name in reversed(TABLES):
        if name in present:
            op.drop_table(name)
