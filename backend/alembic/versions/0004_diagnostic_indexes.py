"""add composite registration and diagnostic timeline indexes"""
from alembic import op
import sqlalchemy as sa

revision="0004";down_revision="0003";branch_labels=None;depends_on=None

INDEXES=[
    ("vehicle_profiles","ix_vehicle_profiles_registration_country_fingerprint",["registration_country","registration_fingerprint"]),
    ("diagnostic_sessions","ix_diagnostic_sessions_created_at",["created_at"]),
    ("diagnostic_images","ix_diagnostic_images_created_at",["created_at"]),
    ("ai_calls","ix_ai_calls_created_at",["created_at"]),
]

def upgrade():
    bind=op.get_bind()
    for table,name,columns in INDEXES:
        if name not in {item["name"] for item in sa.inspect(bind).get_indexes(table)}:op.create_index(name,table,columns)

def downgrade():
    bind=op.get_bind()
    for table,name,_ in reversed(INDEXES):
        if name in {item["name"] for item in sa.inspect(bind).get_indexes(table)}:op.drop_index(name,table_name=table)
