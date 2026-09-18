"""Tavily research cache and confirmed repair outcomes.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
from app.database.models import Base

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None
TABLES = ("research_cache", "diagnostic_outcomes")


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
