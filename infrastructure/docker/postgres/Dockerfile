# Mrittika AI needs PostGIS (§11 cadastral geometry) and pgvector (§10 RAG
# semantic retrieval) in the SAME database. No official image ships both.
#
# Base choice matters on Apple Silicon: `postgis/postgis:16-3.4` publishes no
# arm64 manifest, so Docker silently emulates amd64 -- slow, and its apt
# traffic tripped a network filter on this network. The official
# `postgres:16-bookworm` image IS multi-arch and already configures the PGDG
# apt repo, which carries both extensions as prebuilt packages. So we install
# rather than compile: arm64-native, faster, and version-pinned by the distro.
FROM postgres:16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16-postgis-3 \
        postgresql-16-postgis-3-scripts \
        postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# Runs once, on first init of an empty data directory.
COPY init-extensions.sql /docker-entrypoint-initdb.d/10-init-extensions.sql
