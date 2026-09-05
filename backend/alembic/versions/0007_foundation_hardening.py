"""authentication, VIN protection, provenance and safe DTC classification

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    additions = {
        "users": (
            sa.Column("password_hash", sa.String(300), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        ),
        "vehicle_profiles": (
            sa.Column("vin_encrypted", sa.Text(), nullable=True),
            sa.Column("vin_fingerprint", sa.String(64), nullable=True),
            sa.Column("vin_last_six", sa.String(6), nullable=True),
        ),
        "dtcs": (sa.Column("definition_type", sa.String(40), nullable=False, server_default="unknown"),),
        "diagnostic_hypotheses": (
            sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("verification_status", sa.String(30), nullable=False, server_default="unverified"),
        ),
        "diagnostic_steps": (
            sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("verification_status", sa.String(30), nullable=False, server_default="unverified"),
        ),
    }
    for table, columns in additions.items():
        existing = _columns(inspector, table)
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)

    inspector = sa.inspect(bind)
    if "garage_memberships" not in inspector.get_table_names():
        op.create_table(
            "garage_memberships",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("garage_id", sa.String(36), sa.ForeignKey("garages.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "garage_id", name="uq_membership_user_garage"),
        )
        op.create_index("ix_garage_memberships_user_id", "garage_memberships", ["user_id"])
        op.create_index("ix_garage_memberships_garage_id", "garage_memberships", ["garage_id"])
    if "auth_sessions" not in inspector.get_table_names():
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("garage_id", sa.String(36), sa.ForeignKey("garages.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_garage_id", "auth_sessions", ["garage_id"])
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("vehicle_profiles")}
    if "ix_vehicle_profiles_vin_fingerprint" not in indexes:
        op.create_index("ix_vehicle_profiles_vin_fingerprint", "vehicle_profiles", ["vin_fingerprint"])
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("dtcs")}
    if "ix_dtcs_definition_type" not in indexes:
        op.create_index("ix_dtcs_definition_type", "dtcs", ["definition_type"])

    bind.execute(sa.text("UPDATE dtcs SET definition_type='generic_standardized' WHERE confidence_tier IN ('generic_standard','demo_verified') AND manufacturer_specific=false"))
    bind.execute(sa.text("UPDATE dtcs SET definition_type='unknown', generic_description='', source_id=NULL, probable_family_fr=NULL, control_points_fr=NULL, approximation_source_url=NULL, approximation_method=NULL, confidence_tier='quarantined' WHERE confidence_tier IN ('approximation_family','manufacturer_indicative','manufacturer_exact_internet')"))

    users = bind.execute(sa.text("SELECT id, garage_id, role, created_at, updated_at FROM users")).mappings()
    membership = sa.table(
        "garage_memberships",
        sa.column("id"), sa.column("user_id"), sa.column("garage_id"), sa.column("role"),
        sa.column("is_active"), sa.column("created_at"), sa.column("updated_at"),
    )
    import uuid
    from datetime import datetime, timezone
    for user in users:
        exists = bind.execute(sa.text("SELECT 1 FROM garage_memberships WHERE user_id=:uid AND garage_id=:gid"), {"uid": user["id"], "gid": user["garage_id"]}).first()
        if not exists:
            timestamp = user["created_at"] or datetime.now(timezone.utc)
            bind.execute(membership.insert().values(id=str(uuid.uuid4()), user_id=user["id"], garage_id=user["garage_id"], role=user["role"] if user["role"] in {"admin", "technician"} else "technician", is_active=True, created_at=timestamp, updated_at=user["updated_at"] or timestamp))

    if "vin" in _columns(sa.inspect(bind), "vehicle_profiles"):
        from app.modules.vehicle_resolution.services.security import protector
        rows = bind.execute(sa.text("SELECT id, vin FROM vehicle_profiles WHERE vin IS NOT NULL AND vin != ''")).mappings()
        for row in rows:
            normalized = "".join(character for character in row["vin"].upper() if character.isalnum())
            bind.execute(sa.text("UPDATE vehicle_profiles SET vin=NULL, vin_encrypted=:encrypted, vin_fingerprint=:fingerprint, vin_last_six=:last_six WHERE id=:id"), {"encrypted": protector.encrypt(normalized), "fingerprint": protector.fingerprint(normalized), "last_six": normalized[-6:], "id": row["id"]})


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "auth_sessions" in inspector.get_table_names():
        op.drop_table("auth_sessions")
    if "garage_memberships" in inspector.get_table_names():
        op.drop_table("garage_memberships")
    for table, columns in (
        ("diagnostic_steps", ("verification_status", "source_references")),
        ("diagnostic_hypotheses", ("verification_status", "source_references")),
        ("dtcs", ("definition_type",)),
        ("vehicle_profiles", ("vin_last_six", "vin_fingerprint", "vin_encrypted")),
        ("users", ("is_active", "password_hash")),
    ):
        existing = _columns(sa.inspect(bind), table)
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
