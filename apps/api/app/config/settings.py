"""Typed application settings, loaded from the environment (§61).

Secrets are never defaulted to a usable value: JWT_SECRET_KEY has no default at
all, so a misconfigured deployment fails at startup rather than silently
signing tokens with a key that is in the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    auth_state_redis_url: str | None = None
    login_rate_limit_failures: int = 5
    login_rate_limit_ip_failures: int = 20
    login_rate_limit_window_seconds: int = 60
    ai_query_rate_limit_user: int = Field(default=30, ge=1)
    ai_query_rate_limit_ip: int = Field(default=60, ge=1)
    ai_query_rate_limit_window_seconds: int = Field(default=60, ge=1)
    ai_query_daily_quota: int = Field(default=200, ge=1)

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
    #: OCR processes the worker runs at once. Celery defaults to one per CPU --
    #: 14 on the development Mac -- and each process loads its own OCR model,
    #: which with the default detector peaks at 11-19 GB. With only two running,
    #: swap filled to 18.8 of 20.5 GB. PaddlePaddle already uses several threads
    #: per inference, so more processes do not finish work sooner.
    worker_concurrency: int = 1
    #: Celery pool. None picks per platform in app/worker.py -- "solo" on
    #: macOS, where forking a process that has already started PaddlePaddle's
    #: thread pool segfaults the child. Set explicitly to override.
    worker_pool: str | None = None
    #: Replace a worker process after any task that leaves it above this RSS.
    #: The server text detector grows a process to 11-19 GB and never gives it
    #: back; recycling returns it to the OS between documents. A mobile-detector
    #: process stays under this and is kept, so its model is not reloaded.
    worker_max_memory_mb: int = 4096
    #: None = PaddleOCR's default detector (PP-OCRv5_server_det). See
    #: DETECTION_MODEL in services/ai-worker/ocr/provider.py for the trade-off.
    ocr_detection_model: str | None = None
    #: Scope extraction with the YOLO layout detector. Off: it measured +0.001
    #: F1 (docs/ai-pipeline.md), and costs a model load per worker.
    use_yolo: bool = False
    #: Nightly retrain check (app/tasks/retrain_scheduler.py).
    retrain_scheduler_enabled: bool = True
    #: ACCEPTED corrections since the last run needed before retraining.
    retrain_min_samples: int = 50
    #: pg_featureserv, reached only through /api/v1/geo/features.
    pg_featureserv_url: str = "http://localhost:9000"

    # ── providers (§81) ───────────────────────────────────────────────────
    # Monitoring (§74). A scrape token, because Prometheus cannot hold a JWT:
    # it has no login and its bearer credentials are static. Unset means only
    # analytics:view can read /metrics, which is the safe default -- an
    # unauthenticated metrics endpoint publishes workload and processing state.
    metrics_scrape_token: str | None = None

    # LRMS / DILRMP delivery (§14). Approved records are queued in an outbox
    # and delivered through one adapter:
    #   file      -- write each record as JSON into lrms_outbox_dir, the drop
    #                folder a state LRMS batch import (or SFTP sync) collects
    #   http      -- POST each record to lrms_endpoint with a bearer token
    #   disabled  -- queue only; nothing leaves the system
    lrms_adapter: str = "file"
    lrms_outbox_dir: str = str(REPO_ROOT / "var" / "lrms-outbox")
    lrms_endpoint: str | None = None
    lrms_api_token: str | None = None
    lrms_timeout_seconds: float = 15.0

    # Notifications (§19). Absent credentials are not an error: the dispatcher
    # falls back to recording the attempt and the in-app notification is still
    # written. See app/services/notification_service.py.
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    #: TRAI's DLT regime: transactional SMS in India needs a registered
    #: template ID and principal-entity ID, or the operator drops it.
    msg91_auth_key: str | None = None
    msg91_sender_id: str | None = None
    msg91_pe_id: str | None = None
    #: Email (stdlib SMTP). Unset host = no email is attempted.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str | None = None
    smtp_starttls: bool = True
    #: Expo push needs no credentials; a token raises the per-project limits.
    expo_push_enabled: bool = True
    expo_access_token: str | None = None

    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_llm_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768
    #: "ngram" (default: offline, stdlib, lexical) or "gemini" (semantic; needs
    #: GEMINI_API_KEY). Changing it needs a reindex: vectors never mix.
    embedding_provider: str = "ngram"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    # Paddle's native runtime can terminate the entire interpreter on some
    # macOS/ARM builds. Keep it opt-in; the Gemini provider fails normally and
    # is reported to the user instead of taking down the API process.
    ocr_provider: str = "gemini"
    ocr_fallback_provider: str = "gemini"
    #: A PaddleOCR language code, or "auto" to pick the recogniser per page
    #: from hi/te/ta/ka (slower: one pass per candidate). Gemini reads every
    #: script and ignores this.
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

    @model_validator(mode="after")
    def _reject_unsafe_production_defaults(self) -> Settings:
        """Fail closed when a production process still has local credentials."""
        if self.environment.casefold() != "production":
            return self

        problems: list[str] = []
        if len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY must contain at least 32 characters")
        if not self.database_url and self.postgres_password == "change_me_locally":
            problems.append("POSTGRES_PASSWORD still uses the local default")
        if self.minio_secret_key == "change_me_locally":
            problems.append("MINIO_SECRET_KEY still uses the local default")
        if not self.auth_state_redis_url:
            problems.append("AUTH_STATE_REDIS_URL is required for shared auth state")
        if not self.minio_secure:
            problems.append("MINIO_SECURE must be true")
        if not self.cors_origins:
            problems.append("CORS_ALLOW_ORIGINS must contain an HTTPS origin")
        elif any(
            not origin.startswith("https://")
            or "localhost" in origin
            or "127.0.0.1" in origin
            for origin in self.cors_origins
        ):
            problems.append("CORS_ALLOW_ORIGINS must contain only non-local HTTPS origins")

        if problems:
            raise ValueError("unsafe production configuration: " + "; ".join(problems))
        return self

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
