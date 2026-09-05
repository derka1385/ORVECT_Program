"""versioned multi-namespace diagnostic data catalogue

Revision ID: 0008
Revises: 0007
"""

from alembic import op

from app.database.models import Base


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


TABLES = (
    "diagnostic_namespaces",
    "diagnostic_datasets",
    "diagnostic_identifiers",
    "diagnostic_definition_variants",
    "diagnostic_code_aliases",
    "diagnostic_definition_reviews",
    "diagnostic_alias_reviews",
)


def upgrade():
    # 0001 historically calls Base.metadata.create_all, so fresh databases may
    # already contain later tables. checkfirst also keeps upgrades from 0007 safe.
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)

