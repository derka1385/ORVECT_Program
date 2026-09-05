"""Version-specific source rights, conflicts and dataset revocation audit.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
from app.database.models import Base

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None
TABLES = ("diagnostic_source_assessments", "diagnostic_data_conflicts", "diagnostic_dataset_events")


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
