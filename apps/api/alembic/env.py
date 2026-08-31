"""Alembic environment.

Two things worth knowing:

1. The URL comes from app.config.settings, not alembic.ini, so migrations can
   never be pointed at a different database than the app.
2. PostGIS and pgvector create objects Alembic must not try to manage
   (spatial_ref_sys, geometry columns' own indexes). They are filtered out in
   include_object, otherwise every autogenerate emits spurious drops.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
target_metadata = Base.metadata

#: Tables owned by extensions, not by us.
EXTENSION_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns",
                    "raster_columns", "raster_overviews"}

#: Scratch tables created by offline QA tooling (services/gis). They are
#: deliberately outside the migrated schema; without this Alembic emits a DROP
#: for them on every autogenerate.
NON_MIGRATED_TABLES = {"cadastre_staging"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXTENSION_TABLES | NON_MIGRATED_TABLES:
        return False
    # GeoAlchemy2 manages spatial indexes itself; Alembic would fight it.
    if type_ == "index" and name and name.startswith("idx_") and "geom" in name:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
