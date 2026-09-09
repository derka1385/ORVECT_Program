from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./diagnostic.db"
    cors_origins: str = "http://localhost:3000"
    llm_provider: str = "mock"
    diagnostic_exploration_enabled: bool = False
    max_upload_bytes: int = 1_048_576
    max_request_bytes: int = 25_000_000
    log_level: str = "INFO"
    vin_encryption_key: str = ""
    vin_fingerprint_secret: str = ""
    development_secret: str = "diagpilot-local-development-only"
    auth_session_ttl_hours: int = 12
    auth_provider: Literal["legacy", "firebase"] = "legacy"
    firebase_project_id: str = ""
    firebase_self_signup_enabled: bool = False
    firebase_check_revoked: bool = True
    demo_access_without_login: bool = True
    demo_admin_email: str = "admin@example.com"
    demo_admin_password: str = ""
    demo_technician_email: str = "technician@example.com"
    demo_technician_password: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    vin_provider: str = "mock"
    nhtsa_vpic_enabled: bool = False
    vin_provider_timeout_seconds: float = 10
    vin_cache_ttl_days: int = 30
    vin_retention_days: int = 365
    vin_rate_limit_per_minute: int = 30
    autoref_api_key: str = ""
    autoref_api_url: str = "https://api-gateway.autoref.eu"
    autoref_timeout_seconds: float = 15
    autoref_max_candidates: int = 3
    registration_provider: str = "mock"
    registration_api_url: str = ""
    registration_api_key: str = ""
    registration_api_timeout_seconds: float = 12
    vehicle_provider_primary: str = "mock"
    vehicle_provider_fallbacks: str = ""
    aaa_data_api_url: str = ""
    aaa_data_api_key: str = ""
    tecalliance_api_url: str = ""
    tecalliance_api_key: str = ""
    auto_ways_api_url: str = ""
    auto_ways_api_key: str = ""
    vehicle_lookup_timeout_ms: int = 8000
    vehicle_lookup_cache_ttl_seconds: int = 86400
    vehicle_lookup_enable_mock: bool = False
    vehicle_confidence_reliable: float = .90
    vehicle_confidence_recommended: float = .70
    vehicle_confidence_ambiguous: float = .40
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-3.1-flash-lite"
    gemini_model_reasoning: str = "gemini-3.5-flash"
    gemini_timeout_seconds: float = 45
    gemini_max_output_tokens: int = 8192
    gemini_rate_limit_per_minute: int = 10
    diagnostic_image_dir: str = "./private_images"
    diagnostic_image_retention_days: int = 90
    max_diagnostic_images: int = 8
    max_image_bytes: int = 8_000_000
    max_image_total_bytes: int = 24_000_000
    max_image_dimension: int = 2400
    max_image_pixels: int = 16_000_000
    max_diagnostic_fault_codes: int = 30
    max_diagnostic_measurements: int = 100
    max_diagnostic_observations: int = 200
    default_page_size: int = 50
    max_page_size: int = 100
    keep_original_images: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value):
        if isinstance(value, str) and value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if isinstance(value, str) and value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @model_validator(mode="after")
    def production_secrets_are_required(self):
        if self.auth_provider == "firebase" and not self.firebase_project_id:
            raise ValueError("FIREBASE_PROJECT_ID is required for Firebase authentication")
        if self.app_environment == "production":
            missing = [
                name
                for name, value in (
                    ("VIN_ENCRYPTION_KEY", self.vin_encryption_key),
                    ("VIN_FINGERPRINT_SECRET", self.vin_fingerprint_secret),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Production configuration missing required secrets: {', '.join(missing)}")
            if self.development_secret == "diagpilot-local-development-only":
                raise ValueError("DEVELOPMENT_SECRET must be replaced in production")
            if self.demo_admin_password or self.demo_technician_password:
                raise ValueError("Demo passwords must be empty in production")
            if self.bootstrap_admin_password and not self.bootstrap_admin_email:
                raise ValueError("BOOTSTRAP_ADMIN_EMAIL is required when BOOTSTRAP_ADMIN_PASSWORD is set")
            if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 16:
                raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 16 characters")
        if self.max_request_bytes < self.max_upload_bytes:
            raise ValueError("MAX_REQUEST_BYTES must be greater than or equal to MAX_UPLOAD_BYTES")
        return self

settings = Settings()
