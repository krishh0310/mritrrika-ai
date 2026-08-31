"""Typed application settings, loaded from the environment (§61).

Secrets are never defaulted to a usable value: JWT_SECRET_KEY has no default at
all, so a misconfigured deployment fails at startup rather than silently
signing tokens with a key that is in the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"

    # ── database ──────────────────────────────────────────────────────────
    postgres_user: str = "mrittika"
    postgres_password: str = "change_me_locally"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mrittika"
    database_url: str | None = None

    # ── auth ──────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── storage ───────────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "change_me_locally"
    minio_secure: bool = False
    minio_bucket_documents: str = "mrittika-documents"
    minio_bucket_derived: str = "mrittika-derived"

    # ── queue ─────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── providers (§81) ───────────────────────────────────────────────────
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_llm_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    ocr_provider: str = "paddle"
    ocr_fallback_provider: str = "gemini"
    ocr_lang: str = "hi"

    # ── model versions recorded on every prediction (§64) ─────────────────
    model_version_ocr: str = "ocr-v1"
    model_version_layout: str = "layout-v1"
    model_version_extractor: str = "extractor-v1"
    model_version_confidence: str = "confidence-v1"
    model_version_anomaly: str = "anomaly-v1"

    # ── uploads (§61) ─────────────────────────────────────────────────────
    max_upload_bytes: int = 26_214_400
    allowed_upload_mime: str = "application/pdf,image/png,image/jpeg"

    # ── web ───────────────────────────────────────────────────────────────
    cors_allow_origins: str = "http://localhost:3000"

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, v: str) -> str:
        if "do_not_use_this" in v or v.strip() == "":
            raise ValueError(
                "JWT_SECRET_KEY is still the placeholder from .env.example. "
                "Generate one: python -c \"import secrets; "
                "print(secrets.token_urlsafe(64))\""
            )
        return v

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_mime_set(self) -> set[str]:
        return {m.strip() for m in self.allowed_upload_mime.split(",") if m.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
