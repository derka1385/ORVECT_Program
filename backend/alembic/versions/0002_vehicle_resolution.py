"""add VIN resolution and canonical vehicle configuration tables"""
from alembic import op
from app.database.models import Base
revision="0002"
down_revision="0001"
branch_labels=None
depends_on=None
TABLES=["vin_resolution_requests","vehicle_configuration_candidates","vehicle_configurations","ecu_configurations","vehicle_resolution_events"]
def upgrade():
    bind=op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind,checkfirst=True)
def downgrade():
    bind=op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind,checkfirst=True)
