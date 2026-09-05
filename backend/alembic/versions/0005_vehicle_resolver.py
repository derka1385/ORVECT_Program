"""vehicle resolver technical identity

Revision ID: 0005_vehicle_resolver
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision="0005";down_revision="0004";branch_labels=None;depends_on=None

def upgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    for table in ("vehicle_configuration_candidates","vehicle_configurations"):
        existing={column["name"] for column in inspector.get_columns(table)}
        columns=(sa.Column("tecdoc_k_type",sa.String(100),nullable=True),sa.Column("cnit",sa.String(100),nullable=True),sa.Column("type_mine",sa.String(100),nullable=True),sa.Column("engine_ecu_manufacturer",sa.String(120),nullable=True),sa.Column("engine_ecu_model",sa.String(120),nullable=True))
        for column in columns:
            if column.name not in existing: op.add_column(table,column)
        indexes={index["name"] for index in inspector.get_indexes(table)}
        for name,column in ((f"ix_{table}_tecdoc_k_type","tecdoc_k_type"),(f"ix_{table}_cnit","cnit")):
            if name not in indexes: op.create_index(name,table,[column])
    table="vehicle_configurations";existing={column["name"] for column in inspector.get_columns(table)}
    columns=(sa.Column("engine_code_from_provider",sa.String(100),nullable=True),sa.Column("engine_code_confirmed_by_user",sa.String(100),nullable=True),sa.Column("providers_used",sa.JSON(),nullable=False,server_default="[]"),sa.Column("field_provenance",sa.JSON(),nullable=False,server_default="{}"))
    for column in columns:
        if column.name not in existing: op.add_column(table,column)

def downgrade():
    for column in ("field_provenance","providers_used","engine_code_confirmed_by_user","engine_code_from_provider"):op.drop_column("vehicle_configurations",column)
    for table in ("vehicle_configurations","vehicle_configuration_candidates"):
        op.drop_index(f"ix_{table}_cnit",table_name=table);op.drop_index(f"ix_{table}_tecdoc_k_type",table_name=table)
        for column in ("engine_ecu_model","engine_ecu_manufacturer","type_mine","cnit","tecdoc_k_type"):op.drop_column(table,column)
