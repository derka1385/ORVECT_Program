"""Bind Firebase identities to existing ORVECT users without moving diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = "0010_firebase_identities"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    # The initial historical migration creates all current metadata tables.
    if sa.inspect(op.get_bind()).has_table("firebase_identities"):
        return
    op.create_table("firebase_identities",
        sa.Column("uid", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True))


def downgrade():
    op.drop_table("firebase_identities")
