"""Tavily research cache (Orvect knowledge-first research layer).

Revision ID: 0012
Revises: 0011
"""
from alembic import op
from app.database.models import Base

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None
TABLES = ("research_cache",)


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
