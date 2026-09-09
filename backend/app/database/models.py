import enum, uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass

class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Garage(Base, Timestamps):
    __tablename__="garages"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); name: Mapped[str]=mapped_column(String(200))
class User(Base, Timestamps):
    __tablename__="users"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"), index=True); email: Mapped[str]=mapped_column(String(320), unique=True); display_name: Mapped[str]=mapped_column(String(160)); role: Mapped[str]=mapped_column(String(20), default="technician"); password_hash: Mapped[str|None]=mapped_column(String(300)); is_active: Mapped[bool]=mapped_column(Boolean,default=True)
class GarageMembership(Base, Timestamps):
    __tablename__="garage_memberships"; __table_args__=(UniqueConstraint("user_id","garage_id",name="uq_membership_user_garage"),); id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"),index=True); role: Mapped[str]=mapped_column(String(20)); is_active: Mapped[bool]=mapped_column(Boolean,default=True)
class FirebaseIdentity(Base):
    __tablename__ = "firebase_identities"
    uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)

class AuthSession(Base):
    # Revision 0007 creates both the unique constraint and the lookup index.
    __table_args__ = (UniqueConstraint("token_hash", name="auth_sessions_token_hash_key"),)
    __tablename__="auth_sessions"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); token_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True); user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"),index=True); expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VehicleProfile(Base, Timestamps):
    __table_args__ = (Index("ix_vehicle_profiles_registration_country_fingerprint", "registration_country", "registration_fingerprint"),)
    __tablename__="vehicle_profiles"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"), index=True); make: Mapped[str]=mapped_column(String(100)); model: Mapped[str]=mapped_column(String(100)); year: Mapped[int]=mapped_column(Integer); market: Mapped[str]=mapped_column(String(50), default="generic_demo"); engine_name: Mapped[str]=mapped_column(String(100)); engine_code: Mapped[str]=mapped_column(String(100)); fuel_type: Mapped[str]=mapped_column(String(40), default="gasoline"); transmission: Mapped[str]=mapped_column(String(40), default="manual"); vin: Mapped[str|None]=mapped_column(String(32)); vin_encrypted: Mapped[str|None]=mapped_column(Text); vin_fingerprint: Mapped[str|None]=mapped_column(String(64),index=True); vin_last_six: Mapped[str|None]=mapped_column(String(6)); registration_encrypted: Mapped[str|None]=mapped_column(Text); registration_fingerprint: Mapped[str|None]=mapped_column(String(64),index=True); registration_last_four: Mapped[str|None]=mapped_column(String(4)); registration_country: Mapped[str|None]=mapped_column(String(2)); ecu_reference: Mapped[str|None]=mapped_column(String(100)); notes: Mapped[str]=mapped_column(Text, default=""); is_demo_vehicle: Mapped[bool]=mapped_column(Boolean, default=False)
class DiagnosticTroubleCode(Base, Timestamps):
    __tablename__="dtcs"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); code: Mapped[str]=mapped_column(String(10), unique=True, index=True); category: Mapped[str]=mapped_column(String(50)); generic_description: Mapped[str]=mapped_column(String(300)); manufacturer_specific: Mapped[bool]=mapped_column(Boolean, default=False); affected_system: Mapped[str]=mapped_column(String(100)); severity_hint: Mapped[str]=mapped_column(String(30)); source_id: Mapped[str|None]=mapped_column(ForeignKey("knowledge_sources.id"))
    confidence_tier: Mapped[str]=mapped_column(String(30), default="unknown", index=True); definition_type: Mapped[str]=mapped_column(String(40),default="unknown",index=True); probable_family_fr: Mapped[str|None]=mapped_column(String(300)); control_points_fr: Mapped[str|None]=mapped_column(Text); approximation_source_url: Mapped[str|None]=mapped_column(String(500)); approximation_method: Mapped[str|None]=mapped_column(String(300))
class KnowledgeSource(Base, Timestamps):
    __tablename__="knowledge_sources"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); title: Mapped[str]=mapped_column(String(250)); source_type: Mapped[str]=mapped_column(String(60)); publisher: Mapped[str]=mapped_column(String(120)); version: Mapped[str]=mapped_column(String(40)); publication_date: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); license_type: Mapped[str]=mapped_column(String(60)); source_url: Mapped[str|None]=mapped_column(String(500)); local_file_path: Mapped[str|None]=mapped_column(String(500)); checksum: Mapped[str|None]=mapped_column(String(64), unique=True); trust_level: Mapped[str]=mapped_column(String(30)); review_status: Mapped[str]=mapped_column(String(30))
class KnowledgeItem(Base, Timestamps):
    __tablename__="knowledge_items"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); source_id: Mapped[str]=mapped_column(ForeignKey("knowledge_sources.id")); vehicle_profile_id: Mapped[str|None]=mapped_column(ForeignKey("vehicle_profiles.id")); dtc_id: Mapped[str|None]=mapped_column(ForeignKey("dtcs.id")); system: Mapped[str]=mapped_column(String(100)); component: Mapped[str]=mapped_column(String(100)); item_type: Mapped[str]=mapped_column(String(40)); title: Mapped[str]=mapped_column(String(250)); content: Mapped[str]=mapped_column(Text); structured_data: Mapped[dict]=mapped_column(JSON, default=dict); confidence_level: Mapped[str]=mapped_column(String(20)); human_verified: Mapped[bool]=mapped_column(Boolean, default=False)
class DiagnosticRule(Base, Timestamps):
    __tablename__="diagnostic_rules"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); vehicle_profile_id: Mapped[str|None]=mapped_column(ForeignKey("vehicle_profiles.id")); dtc_id: Mapped[str|None]=mapped_column(ForeignKey("dtcs.id")); name: Mapped[str]=mapped_column(String(200)); conditions: Mapped[dict]=mapped_column(JSON); action: Mapped[dict]=mapped_column(JSON); priority: Mapped[int]=mapped_column(Integer); enabled: Mapped[bool]=mapped_column(Boolean, default=True); source_ids: Mapped[list]=mapped_column(JSON, default=list); human_verified: Mapped[bool]=mapped_column(Boolean, default=False)
class DiagnosticSession(Base, Timestamps):
    __table_args__ = (Index("ix_diagnostic_sessions_created_at", "created_at"),)
    __tablename__="diagnostic_sessions"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"), index=True); technician_id: Mapped[str]=mapped_column(ForeignKey("users.id")); vehicle_profile_id: Mapped[str]=mapped_column(ForeignKey("vehicle_profiles.id")); status: Mapped[str]=mapped_column(String(30), default="draft",index=True); mileage: Mapped[int|None]=mapped_column(Integer); customer_complaint: Mapped[str]=mapped_column(Text, default=""); observed_symptoms: Mapped[str]=mapped_column(Text, default=""); appearance_circumstances: Mapped[str]=mapped_column(Text,default=""); urgency_level: Mapped[str|None]=mapped_column(String(20)); current_summary: Mapped[str]=mapped_column(Text,default=""); prompt_version: Mapped[str|None]=mapped_column(String(30)); ai_model: Mapped[str|None]=mapped_column(String(100)); analysis_context_hash: Mapped[str|None]=mapped_column(String(64),index=True); analysis_started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); vehicle: Mapped[VehicleProfile]=relationship()
class DiagnosticObservation(Base):
    __tablename__="diagnostic_observations"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"), index=True); observation_type: Mapped[str]=mapped_column(String(40)); key: Mapped[str]=mapped_column(String(100)); value: Mapped[dict]=mapped_column(JSON); unit: Mapped[str|None]=mapped_column(String(30)); source: Mapped[str]=mapped_column(String(80)); observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class DiagnosticHypothesis(Base, Timestamps):
    __tablename__="diagnostic_hypotheses"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"), index=True); title: Mapped[str]=mapped_column(String(200)); suspected_component: Mapped[str]=mapped_column(String(100)); probability_score: Mapped[float]=mapped_column(Float); confidence_label: Mapped[str]=mapped_column(String(20)); reasoning: Mapped[str]=mapped_column(Text); supporting_evidence: Mapped[list]=mapped_column(JSON); contradicting_evidence: Mapped[list]=mapped_column(JSON); source_ids: Mapped[list]=mapped_column(JSON); source_references: Mapped[list]=mapped_column(JSON,default=list); verification_status: Mapped[str]=mapped_column(String(30),default="unverified"); status: Mapped[str]=mapped_column(String(30), default="active")
class DiagnosticStep(Base):
    __tablename__="diagnostic_steps"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"), index=True); step_order: Mapped[int]=mapped_column(Integer); title: Mapped[str]=mapped_column(String(250)); objective: Mapped[str]=mapped_column(Text); instructions: Mapped[list]=mapped_column(JSON); required_tools: Mapped[list]=mapped_column(JSON); expected_results: Mapped[list]=mapped_column(JSON); safety_notes: Mapped[list]=mapped_column(JSON); source_ids: Mapped[list]=mapped_column(JSON); source_references: Mapped[list]=mapped_column(JSON,default=list); verification_status: Mapped[str]=mapped_column(String(30),default="unverified"); status: Mapped[str]=mapped_column(String(30), default="pending"); result: Mapped[dict|None]=mapped_column(JSON); technician_comment: Mapped[str|None]=mapped_column(Text); hypotheses_before: Mapped[list]=mapped_column(JSON,default=list); hypotheses_after: Mapped[list]=mapped_column(JSON,default=list); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class DiagnosticEvent(Base):
    __tablename__="diagnostic_events"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"), index=True); event_type: Mapped[str]=mapped_column(String(60)); payload: Mapped[dict]=mapped_column(JSON); actor_type: Mapped[str]=mapped_column(String(30)); actor_id: Mapped[str|None]=mapped_column(String(36)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class AICall(Base):
    __table_args__ = (Index("ix_ai_calls_created_at", "created_at"),)
    __tablename__="ai_calls"; id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"),index=True); provider: Mapped[str]=mapped_column(String(50)); model: Mapped[str]=mapped_column(String(100)); operation_type: Mapped[str]=mapped_column(String(40),default="initial_analysis"); status: Mapped[str]=mapped_column(String(30),default="completed",index=True); schema_version: Mapped[str]=mapped_column(String(20),default="1.0"); prompt_version: Mapped[str]=mapped_column(String(30)); request_id: Mapped[str]=mapped_column(String(36)); input_hash: Mapped[str]=mapped_column(String(64),index=True); output_hash: Mapped[str|None]=mapped_column(String(64)); output_payload: Mapped[dict|None]=mapped_column(JSON); validation_status: Mapped[str]=mapped_column(String(30)); error_safe: Mapped[str|None]=mapped_column(String(300)); latency_ms: Mapped[int]=mapped_column(Integer); token_usage: Mapped[dict|None]=mapped_column(JSON); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class DiagnosticImage(Base, Timestamps):
    __table_args__ = (Index("ix_diagnostic_images_created_at", "created_at"),)
    __tablename__="diagnostic_images"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); session_id: Mapped[str]=mapped_column(ForeignKey("diagnostic_sessions.id"),index=True); storage_path: Mapped[str]=mapped_column(String(500)); thumbnail_path: Mapped[str]=mapped_column(String(500)); mime_type: Mapped[str]=mapped_column(String(50)); size_bytes: Mapped[int]=mapped_column(Integer); width: Mapped[int]=mapped_column(Integer); height: Mapped[int]=mapped_column(Integer); category: Mapped[str]=mapped_column(String(60)); description: Mapped[str]=mapped_column(Text,default=""); extraction_result: Mapped[dict|None]=mapped_column(JSON); processing_status: Mapped[str]=mapped_column(String(30),default="ready",index=True)

class VinResolutionRequest(Base, Timestamps):
    __tablename__="vin_resolution_requests"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); garage_id: Mapped[str]=mapped_column(ForeignKey("garages.id"),index=True); vehicle_id: Mapped[str|None]=mapped_column(ForeignKey("vehicle_profiles.id"),index=True); vin_encrypted: Mapped[str]=mapped_column(Text); vin_fingerprint: Mapped[str]=mapped_column(String(64),index=True); vin_last_six: Mapped[str]=mapped_column(String(6)); country_code: Mapped[str|None]=mapped_column(String(2)); model_year_hint: Mapped[int|None]=mapped_column(Integer); selected_provider: Mapped[str]=mapped_column(String(60)); provider_version: Mapped[str|None]=mapped_column(String(40)); provider_request_id: Mapped[str|None]=mapped_column(String(100)); status: Mapped[str]=mapped_column(String(40)); error_code: Mapped[str|None]=mapped_column(String(80)); error_message_safe: Mapped[str|None]=mapped_column(String(300)); started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class VehicleConfigurationCandidate(Base, Timestamps):
    __tablename__="vehicle_configuration_candidates"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); resolution_id: Mapped[str]=mapped_column(ForeignKey("vin_resolution_requests.id"),index=True); manufacturer: Mapped[str|None]=mapped_column(String(150)); make: Mapped[str|None]=mapped_column(String(100)); model: Mapped[str|None]=mapped_column(String(100)); generation: Mapped[str|None]=mapped_column(String(100)); model_year: Mapped[int|None]=mapped_column(Integer); production_date: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); first_registration_date: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); market: Mapped[str|None]=mapped_column(String(50)); vehicle_type: Mapped[str|None]=mapped_column(String(80)); body_type: Mapped[str|None]=mapped_column(String(80)); fuel_type: Mapped[str|None]=mapped_column(String(60)); engine_family: Mapped[str|None]=mapped_column(String(100)); engine_name: Mapped[str|None]=mapped_column(String(150)); engine_code: Mapped[str|None]=mapped_column(String(100)); engine_displacement_cc: Mapped[int|None]=mapped_column(Integer); engine_power_kw: Mapped[float|None]=mapped_column(Float); engine_power_hp: Mapped[float|None]=mapped_column(Float); engine_torque_nm: Mapped[float|None]=mapped_column(Float); engine_induction: Mapped[str|None]=mapped_column(String(80)); engine_cylinders: Mapped[int|None]=mapped_column(Integer); transmission_type: Mapped[str|None]=mapped_column(String(80)); transmission_code: Mapped[str|None]=mapped_column(String(100)); transmission_gears: Mapped[int|None]=mapped_column(Integer); drivetrain: Mapped[str|None]=mapped_column(String(80)); emission_standard: Mapped[str|None]=mapped_column(String(80)); engine_type_approval: Mapped[str|None]=mapped_column(String(120)); equipment: Mapped[list]=mapped_column(JSON,default=list); platform: Mapped[str|None]=mapped_column(String(100)); type_variant_version: Mapped[str|None]=mapped_column(String(150)); tecdoc_k_type: Mapped[str|None]=mapped_column(String(100),index=True); cnit: Mapped[str|None]=mapped_column(String(100),index=True); type_mine: Mapped[str|None]=mapped_column(String(100)); engine_ecu_manufacturer: Mapped[str|None]=mapped_column(String(120)); engine_ecu_model: Mapped[str|None]=mapped_column(String(120)); provider_name: Mapped[str]=mapped_column(String(60)); provider_vehicle_id: Mapped[str|None]=mapped_column(String(120)); provider_type_id: Mapped[str|None]=mapped_column(String(120)); confidence_score: Mapped[float]=mapped_column(Float,default=0); missing_critical_fields: Mapped[list]=mapped_column(JSON,default=list); warnings: Mapped[list]=mapped_column(JSON,default=list); field_provenance: Mapped[dict]=mapped_column(JSON,default=dict); is_selected: Mapped[bool]=mapped_column(Boolean,default=False); is_confirmed: Mapped[bool]=mapped_column(Boolean,default=False); confirmed_by_user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id")); confirmed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class VehicleConfiguration(Base, Timestamps):
    __tablename__="vehicle_configurations"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); vehicle_id: Mapped[str]=mapped_column(ForeignKey("vehicle_profiles.id"),unique=True,index=True); selected_candidate_id: Mapped[str|None]=mapped_column(ForeignKey("vehicle_configuration_candidates.id")); manufacturer: Mapped[str|None]=mapped_column(String(150)); make: Mapped[str|None]=mapped_column(String(100)); model: Mapped[str|None]=mapped_column(String(100)); generation: Mapped[str|None]=mapped_column(String(100)); model_year: Mapped[int|None]=mapped_column(Integer); production_date: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); first_registration_date: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); market: Mapped[str|None]=mapped_column(String(50)); vehicle_type: Mapped[str|None]=mapped_column(String(80)); body_type: Mapped[str|None]=mapped_column(String(80)); fuel_type: Mapped[str|None]=mapped_column(String(60)); engine_family: Mapped[str|None]=mapped_column(String(100)); engine_name: Mapped[str|None]=mapped_column(String(150)); engine_code: Mapped[str|None]=mapped_column(String(100)); engine_code_from_provider: Mapped[str|None]=mapped_column(String(100)); engine_code_confirmed_by_user: Mapped[str|None]=mapped_column(String(100)); engine_displacement_cc: Mapped[int|None]=mapped_column(Integer); engine_power_kw: Mapped[float|None]=mapped_column(Float); engine_power_hp: Mapped[float|None]=mapped_column(Float); engine_torque_nm: Mapped[float|None]=mapped_column(Float); engine_induction: Mapped[str|None]=mapped_column(String(80)); transmission_type: Mapped[str|None]=mapped_column(String(80)); transmission_code: Mapped[str|None]=mapped_column(String(100)); transmission_gears: Mapped[int|None]=mapped_column(Integer); drivetrain: Mapped[str|None]=mapped_column(String(80)); emission_standard: Mapped[str|None]=mapped_column(String(80)); engine_type_approval: Mapped[str|None]=mapped_column(String(120)); equipment: Mapped[list]=mapped_column(JSON,default=list); platform: Mapped[str|None]=mapped_column(String(100)); type_variant_version: Mapped[str|None]=mapped_column(String(150)); tecdoc_k_type: Mapped[str|None]=mapped_column(String(100),index=True); cnit: Mapped[str|None]=mapped_column(String(100),index=True); type_mine: Mapped[str|None]=mapped_column(String(100)); engine_ecu_manufacturer: Mapped[str|None]=mapped_column(String(120)); engine_ecu_model: Mapped[str|None]=mapped_column(String(120)); providers_used: Mapped[list]=mapped_column(JSON,default=list); field_provenance: Mapped[dict]=mapped_column(JSON,default=dict); precision_level: Mapped[str]=mapped_column(String(40),default="unknown"); confidence_score: Mapped[float]=mapped_column(Float,default=0); confirmed_by_user: Mapped[bool]=mapped_column(Boolean,default=False); confirmed_by_user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id")); confirmed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class EcuConfiguration(Base, Timestamps):
    __tablename__="ecu_configurations"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); vehicle_configuration_id: Mapped[str]=mapped_column(ForeignKey("vehicle_configurations.id"),index=True); ecu_type: Mapped[str]=mapped_column(String(80)); ecu_address: Mapped[str|None]=mapped_column(String(80)); ecu_manufacturer: Mapped[str|None]=mapped_column(String(120)); part_number: Mapped[str|None]=mapped_column(String(120)); hardware_number: Mapped[str|None]=mapped_column(String(120)); software_number: Mapped[str|None]=mapped_column(String(120)); calibration_id: Mapped[str|None]=mapped_column(String(120)); protocol: Mapped[str|None]=mapped_column(String(80)); source: Mapped[str]=mapped_column(String(60)); confidence_score: Mapped[float]=mapped_column(Float,default=0); first_detected_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); last_detected_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VehicleResolutionEvent(Base):
    __tablename__="vehicle_resolution_events"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); resolution_id: Mapped[str]=mapped_column(ForeignKey("vin_resolution_requests.id"),index=True); vehicle_id: Mapped[str|None]=mapped_column(ForeignKey("vehicle_profiles.id")); event_type: Mapped[str]=mapped_column(String(80)); payload: Mapped[dict]=mapped_column(JSON,default=dict); actor_type: Mapped[str]=mapped_column(String(30)); actor_id: Mapped[str|None]=mapped_column(String(36)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


# Versioned diagnostic-data catalogue.  The legacy ``dtcs`` table remains a
# read-compatible SAE catalogue while OEM datasets are migrated to this model.
class DiagnosticNamespace(Base, Timestamps):
    __tablename__ = "diagnostic_namespaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), index=True)
    brand_group: Mapped[str | None] = mapped_column(String(120), index=True)
    code_system: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DiagnosticDataset(Base, Timestamps):
    __tablename__ = "diagnostic_datasets"
    __table_args__ = (
        UniqueConstraint("namespace_id", "name", "version", name="uq_diagnostic_dataset_version"),
        UniqueConstraint("checksum", name="uq_diagnostic_dataset_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    namespace_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_namespaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(80))
    adapter_type: Mapped[str] = mapped_column(String(40))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="staged", index=True)
    legal_use_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    documented_available_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_definition_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_definition_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    dataset_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class DiagnosticIdentifier(Base, Timestamps):
    __tablename__ = "diagnostic_identifiers"
    __table_args__ = (
        UniqueConstraint("namespace_id", "normalized_code", name="uq_diagnostic_identifier_namespace_code"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    namespace_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_namespaces.id"), index=True)
    normalized_code: Mapped[str] = mapped_column(String(80), index=True)
    canonical_display_code: Mapped[str] = mapped_column(String(100))
    code_type: Mapped[str] = mapped_column(String(40), index=True)
    manufacturer_specific_code: Mapped[str | None] = mapped_column(String(100))


class DiagnosticDefinitionVariant(Base, Timestamps):
    __tablename__ = "diagnostic_definition_variants"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_record_id", name="uq_diagnostic_definition_dataset_record"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identifier_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_identifiers.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_datasets.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    external_record_id: Mapped[str] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(120), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), index=True)
    vehicle_platform: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(120), index=True)
    model_year_from: Mapped[int | None] = mapped_column(Integer)
    model_year_to: Mapped[int | None] = mapped_column(Integer)
    engine_code: Mapped[str | None] = mapped_column(String(100), index=True)
    transmission_code: Mapped[str | None] = mapped_column(String(100), index=True)
    ecu_module: Mapped[str | None] = mapped_column(String(120), index=True)
    ecu_identifiers: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text)
    failure_mode: Mapped[str | None] = mapped_column(String(200))
    subtype: Mapped[str | None] = mapped_column(String(160))
    provenance: Mapped[dict] = mapped_column(JSON)
    source_version: Mapped[str] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(String(30), default="unreviewed", index=True)
    promotion_stage: Mapped[str] = mapped_column(String(30), default="quarantined", index=True)
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class DiagnosticCodeAlias(Base, Timestamps):
    __tablename__ = "diagnostic_code_aliases"
    __table_args__ = (
        UniqueConstraint("source_identifier_id", "target_identifier_id", "relationship_type", "dataset_id", name="uq_diagnostic_code_alias"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_identifier_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_identifiers.id"), index=True)
    target_identifier_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_identifiers.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_datasets.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    source_version: Mapped[str] = mapped_column(String(80))
    provenance: Mapped[dict] = mapped_column(JSON)
    verification_status: Mapped[str] = mapped_column(String(30), default="unreviewed", index=True)
    promotion_stage: Mapped[str] = mapped_column(String(30), default="quarantined", index=True)
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False)


class DiagnosticDefinitionReview(Base):
    __tablename__ = "diagnostic_definition_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    definition_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_definition_variants.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(30))
    to_stage: Mapped[str] = mapped_column(String(30))
    reviewer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DiagnosticAliasReview(Base):
    __tablename__ = "diagnostic_alias_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    alias_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_code_aliases.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(30))
    to_stage: Mapped[str] = mapped_column(String(30))
    reviewer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DiagnosticSourceAssessment(Base, Timestamps):
    """Version-specific rights assessment; a repository licence is not a content grant."""
    __tablename__ = "diagnostic_source_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), unique=True)
    source_version: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(60))
    authority_level: Mapped[str] = mapped_column(String(30))
    commercial_use: Mapped[str] = mapped_column(String(30))
    redistribution: Mapped[str] = mapped_column(String(30))
    attribution_requirements: Mapped[str] = mapped_column(Text)
    licence_evidence: Mapped[str] = mapped_column(Text)
    provenance_notes: Mapped[str] = mapped_column(Text)
    independent_origin: Mapped[str] = mapped_column(String(200))
    content_rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    assessed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    revocation_reason: Mapped[str | None] = mapped_column(Text)


class DiagnosticDataConflict(Base, Timestamps):
    __tablename__ = "diagnostic_data_conflicts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identifier_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_identifiers.id"), index=True)
    left_definition_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_definition_variants.id"))
    right_definition_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_definition_variants.id"))
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    competing_claims: Mapped[dict] = mapped_column(JSON)
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class DiagnosticDatasetEvent(Base):
    __tablename__ = "diagnostic_dataset_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_datasets.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
