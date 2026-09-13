-- A database role for GeoServer that can read the published view and nothing
-- else (§18).
--
--   docker exec -i mrittika-postgres psql -U mrittika -d mrittika \
--     -v pw=a-real-password < infrastructure/geoserver/reader-role.sql
--
-- Pass the password WITHOUT surrounding quotes. :'pw' already quotes the
-- variable's value, so wrapping it again makes the quotes part of the
-- password -- which then fails authentication in a way that reads like a
-- wrong password rather than a quoting mistake.
--
-- Deliberately not an Alembic migration: a migration that creates a role has
-- to carry a password, and a password in version control is a password that
-- has leaked. This runs once, at deployment, by a human.
--
-- The GRANTs matter more than the role. GeoServer serves whatever its store
-- can read, so these privileges ARE the authorization boundary -- the reason
-- a WFS GetFeature cannot return an owner's name is that this role cannot
-- SELECT the table it would come from.
--
-- Note on \gexec: psql does not substitute :variables inside a dollar-quoted
-- DO block, so the password would arrive as the literal text ":'pw'". Building
-- the statement with format() and executing it with \gexec substitutes
-- properly, and %L quotes the password against injection.

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE geoserver_reader LOGIN PASSWORD %L', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoserver_reader')
\gexec

SELECT format('ALTER ROLE geoserver_reader LOGIN PASSWORD %L', :'pw')
\gexec

-- Revoke first. The default PUBLIC grant on the schema is what would otherwise
-- let this role read `parcels`, and every name in `owners`, directly.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM geoserver_reader;
REVOKE ALL ON SCHEMA public FROM geoserver_reader;

SELECT format('GRANT CONNECT ON DATABASE %I TO geoserver_reader', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO geoserver_reader;
GRANT SELECT ON gis_published_parcels TO geoserver_reader;

-- PostGIS keeps its metadata here; a spatial layer is unreadable without it,
-- and it exposes no record data.
GRANT SELECT ON geometry_columns TO geoserver_reader;
GRANT SELECT ON spatial_ref_sys  TO geoserver_reader;

-- Anything added to the schema later must not become readable by default.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM geoserver_reader;
