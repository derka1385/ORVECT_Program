"""Canonical root causes, contribution revocation and re-rankable checks.

Revision ID: 0014
Revises: 0013

Idempotent by design. Earlier revisions in this project create tables from the
live ``Base.metadata``, so a database built from scratch already carries these
columns while an existing deployment does not. Adding only what is missing
keeps both paths on the same head.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

STEP_COLUMNS = (
    sa.Column("estimated_difficulty", sa.String(20), nullable=True),
    sa.Column("estimated_minutes", sa.Integer(), nullable=True),
)
CASE_COLUMNS = (
    sa.Column("cause_system", sa.String(60), nullable=True),
    sa.Column("cause_component", sa.String(80), nullable=True),
    sa.Column("cause_position", sa.String(40), nullable=True),
    sa.Column("cause_failure_mode", sa.String(40), nullable=True),
    sa.Column("cause_canonical", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("cause_resolution", sa.String(40), nullable=False, server_default="unresolved"),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
)
INDEXES = (
    ("ix_experience_cases_cause_system", "experience_cases", "cause_system"),
    ("ix_experience_cases_cause_component", "experience_cases", "cause_component"),
    ("ix_experience_cases_cause_canonical", "experience_cases", "cause_canonical"),
    ("ix_experience_cases_revoked_at", "experience_cases", "revoked_at"),
)


def _existing(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table, columns in (("diagnostic_steps", STEP_COLUMNS), ("experience_cases", CASE_COLUMNS)):
        present = _existing(inspector, table)
        for column in columns:
            if column.name not in present:
                op.add_column(table, column.copy())
    for name, table, field in INDEXES:
        if name not in _indexes(inspector, table):
            op.create_index(name, table, [field])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for name, table, _field in reversed(INDEXES):
        if name in _indexes(inspector, table):
            op.drop_index(name, table_name=table)
    for table, columns in (("experience_cases", CASE_COLUMNS), ("diagnostic_steps", STEP_COLUMNS)):
        present = _existing(inspector, table)
        for column in reversed(columns):
            if column.name in present:
                op.drop_column(table, column.name)
