"""Production settings fail closed while local development stays simple."""

from __future__ import annotations

import pytest
from app.config.settings import Settings
from pydantic import ValidationError

BASE = {
    "environment": "production",
    "jwt_secret_key": "a" * 64,
    "database_url": None,
    "postgres_password": "database-secret",
    "minio_secret_key": "object-store-secret",
    "minio_secure": True,
    "auth_state_redis_url": "redis://redis:6379/2",
    "cors_allow_origins": "https://mrittika.example.gov.in",
}


def configured(**overrides) -> Settings:
    return Settings(_env_file=None, **(BASE | overrides))


def test_secure_production_configuration_is_accepted():
    assert configured().environment == "production"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"jwt_secret_key": "too-short-secret"}, "at least 32"),
        ({"postgres_password": "change_me_locally"}, "POSTGRES_PASSWORD"),
        ({"minio_secret_key": "change_me_locally"}, "MINIO_SECRET_KEY"),
        ({"minio_secure": False}, "MINIO_SECURE"),
        ({"auth_state_redis_url": None}, "AUTH_STATE_REDIS_URL"),
        ({"cors_allow_origins": "http://localhost:3000"}, "CORS_ALLOW_ORIGINS"),
    ],
)
def test_unsafe_production_configuration_is_rejected(override, message):
    with pytest.raises(ValidationError, match=message):
        configured(**override)
