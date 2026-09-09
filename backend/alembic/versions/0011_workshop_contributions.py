"""Diagnostic completion, consent, contributions, submissions and analytics."""
from alembic import op
from app.database.models import Base

revision = "0011"
down_revision = "0010_firebase_identities"
branch_labels = None
depends_on = None

TABLES = (
    "diagnostic_data_consents", "diagnostic_completions",
    "diagnostic_contributions", "dtc_submissions", "account_preferences",
    "product_analytics_events",
)


def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
