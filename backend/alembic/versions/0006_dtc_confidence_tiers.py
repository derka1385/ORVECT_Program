"""dtc confidence tiers and approximation fields

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision="0006";down_revision="0005";branch_labels=None;depends_on=None

def upgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    existing={column["name"] for column in inspector.get_columns("dtcs")}
    columns=(
        sa.Column("confidence_tier",sa.String(30),nullable=False,server_default="unknown"),
        sa.Column("probable_family_fr",sa.String(300),nullable=True),
        sa.Column("control_points_fr",sa.Text(),nullable=True),
        sa.Column("approximation_source_url",sa.String(500),nullable=True),
        sa.Column("approximation_method",sa.String(300),nullable=True),
    )
    for column in columns:
        if column.name not in existing: op.add_column("dtcs",column)
    indexes={index["name"] for index in inspector.get_indexes("dtcs")}
    if "ix_dtcs_confidence_tier" not in indexes: op.create_index("ix_dtcs_confidence_tier","dtcs",["confidence_tier"])

def downgrade():
    op.drop_index("ix_dtcs_confidence_tier",table_name="dtcs")
    for column in ("approximation_method","approximation_source_url","control_points_fr","probable_family_fr","confidence_tier"):
        op.drop_column("dtcs",column)
