"""Sign-in by e-mail code and device (QR code) approval.

Revision ID: 0015
Revises: 0014
"""
from alembic import op

from app.database.models import Base

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TABLES = ("login_codes", "device_authorizations")


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
