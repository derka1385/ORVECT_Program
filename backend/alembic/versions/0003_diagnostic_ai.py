"""extend diagnostic cases for multimodal Gemini analysis"""
from alembic import op
import sqlalchemy as sa
from app.database.models import Base

revision="0003"; down_revision="0002"; branch_labels=None; depends_on=None

def upgrade():
    bind=op.get_bind()
    existing={table:{c["name"] for c in sa.inspect(bind).get_columns(table)} for table in ("vehicle_profiles","diagnostic_sessions","diagnostic_steps","ai_calls")}
    for name,column in [
        ("vehicle_profiles",sa.Column("registration_encrypted",sa.Text(),nullable=True)),
        ("vehicle_profiles",sa.Column("registration_fingerprint",sa.String(64),nullable=True)),
        ("vehicle_profiles",sa.Column("registration_last_four",sa.String(4),nullable=True)),
        ("vehicle_profiles",sa.Column("registration_country",sa.String(2),nullable=True)),
        ("diagnostic_sessions",sa.Column("appearance_circumstances",sa.Text(),nullable=False,server_default="")),
        ("diagnostic_sessions",sa.Column("urgency_level",sa.String(20),nullable=True)),
        ("diagnostic_sessions",sa.Column("current_summary",sa.Text(),nullable=False,server_default="")),
        ("diagnostic_sessions",sa.Column("prompt_version",sa.String(30),nullable=True)),
        ("diagnostic_sessions",sa.Column("ai_model",sa.String(100),nullable=True)),
        ("diagnostic_sessions",sa.Column("analysis_context_hash",sa.String(64),nullable=True)),
        ("diagnostic_sessions",sa.Column("analysis_started_at",sa.DateTime(timezone=True),nullable=True)),
        ("diagnostic_steps",sa.Column("hypotheses_before",sa.JSON(),nullable=False,server_default="[]")),
        ("diagnostic_steps",sa.Column("hypotheses_after",sa.JSON(),nullable=False,server_default="[]")),
        ("ai_calls",sa.Column("operation_type",sa.String(40),nullable=False,server_default="initial_analysis")),
        ("ai_calls",sa.Column("status",sa.String(30),nullable=False,server_default="completed")),
        ("ai_calls",sa.Column("schema_version",sa.String(20),nullable=False,server_default="1.0")),
        ("ai_calls",sa.Column("output_payload",sa.JSON(),nullable=True)),
        ("ai_calls",sa.Column("error_safe",sa.String(300),nullable=True)),
    ]:
        if column.name not in existing[name]: op.add_column(name,column)
    technical=[sa.Column("first_registration_date",sa.DateTime(timezone=True)),sa.Column("engine_power_hp",sa.Float()),sa.Column("engine_torque_nm",sa.Float()),sa.Column("engine_induction",sa.String(80)),sa.Column("transmission_gears",sa.Integer()),sa.Column("drivetrain",sa.String(80)),sa.Column("emission_standard",sa.String(80)),sa.Column("engine_type_approval",sa.String(120)),sa.Column("equipment",sa.JSON(),nullable=False,server_default="[]")]
    for table in ("vehicle_configuration_candidates","vehicle_configurations"):
        columns={c["name"] for c in sa.inspect(bind).get_columns(table)}
        for template in technical:
            if template.name not in columns:op.add_column(table,sa.Column(template.name,template.type,nullable=template.nullable,server_default=template.server_default))
    Base.metadata.tables["diagnostic_images"].create(bind=bind,checkfirst=True)
    for table,index,columns in [("vehicle_profiles","ix_vehicle_profiles_registration_fingerprint",["registration_fingerprint"]),("diagnostic_sessions","ix_diagnostic_sessions_status",["status"]),("diagnostic_sessions","ix_diagnostic_sessions_analysis_context_hash",["analysis_context_hash"]),("ai_calls","ix_ai_calls_session_id",["session_id"]),("ai_calls","ix_ai_calls_status",["status"]),("ai_calls","ix_ai_calls_input_hash",["input_hash"])]:
        if index not in {x["name"] for x in sa.inspect(bind).get_indexes(table)}: op.create_index(index,table,columns)

def downgrade():
    bind=op.get_bind()
    for table,index in [("ai_calls","ix_ai_calls_input_hash"),("ai_calls","ix_ai_calls_status"),("ai_calls","ix_ai_calls_session_id"),("diagnostic_sessions","ix_diagnostic_sessions_analysis_context_hash"),("diagnostic_sessions","ix_diagnostic_sessions_status"),("vehicle_profiles","ix_vehicle_profiles_registration_fingerprint")]:
        if index in {x["name"] for x in sa.inspect(bind).get_indexes(table)}: op.drop_index(index,table_name=table)
    Base.metadata.tables["diagnostic_images"].drop(bind=bind,checkfirst=True)
    for table in ("vehicle_configurations","vehicle_configuration_candidates"):
        for column in ("equipment","engine_type_approval","emission_standard","drivetrain","transmission_gears","engine_induction","engine_torque_nm","engine_power_hp","first_registration_date"):
            if column in {c["name"] for c in sa.inspect(bind).get_columns(table)}:op.drop_column(table,column)
    for table,column in [("ai_calls","error_safe"),("ai_calls","output_payload"),("ai_calls","schema_version"),("ai_calls","status"),("ai_calls","operation_type"),("diagnostic_steps","hypotheses_after"),("diagnostic_steps","hypotheses_before"),("diagnostic_sessions","analysis_started_at"),("diagnostic_sessions","analysis_context_hash"),("diagnostic_sessions","ai_model"),("diagnostic_sessions","prompt_version"),("diagnostic_sessions","current_summary"),("diagnostic_sessions","urgency_level"),("diagnostic_sessions","appearance_circumstances"),("vehicle_profiles","registration_country"),("vehicle_profiles","registration_last_four"),("vehicle_profiles","registration_fingerprint"),("vehicle_profiles","registration_encrypted")]:
        if column in {c["name"] for c in sa.inspect(bind).get_columns(table)}: op.drop_column(table,column)
