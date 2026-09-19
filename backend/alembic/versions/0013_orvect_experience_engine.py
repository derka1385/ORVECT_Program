"""ORVECT Experience Engine: workshop outcomes become reusable evidence.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
from app.database.models import Base

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None
TABLES = (
    "hypothesis_state_events",
    "hypothesis_outcomes",
    "experience_cases",
    "experience_patterns",
    "experience_pattern_cases",
)


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
