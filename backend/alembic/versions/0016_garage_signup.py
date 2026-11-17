"""Garage sign-up checked against the company register (SIRET).

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

from app.database.models import Base

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("garages", sa.Column("siret", sa.String(14), nullable=True))
    op.add_column("garages", sa.Column("naf_code", sa.String(6), nullable=True))
    op.add_column("garages", sa.Column("siret_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_garages_siret", "garages", ["siret"])
    Base.metadata.tables["signup_requests"].create(op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["signup_requests"].drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("uq_garages_siret", "garages", type_="unique")
    op.drop_column("garages", "siret_verified_at")
    op.drop_column("garages", "naf_code")
    op.drop_column("garages", "siret")
