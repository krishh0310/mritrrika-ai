# Database

PostgreSQL 16 is the system of record. PostGIS stores parcel geometry and
pgvector is available for authorization-scoped semantic retrieval. MinIO owns
document bytes and derived images; Redis owns temporary rate-limit, token, and
queue state.

The canonical schema and relationship rationale are documented in
[data-model.md](data-model.md). SQLAlchemy models live under
`apps/api/app/models`; Alembic migrations under `apps/api/alembic/versions` are
the only supported way to change a deployed schema.

## Local setup

```bash
docker compose up -d postgres redis minio minio-init
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
.venv/bin/python scripts/seed_demo.py
```

`GET /ready` confirms database connectivity and the required `postgis` and
`vector` extensions. The seed is synthetic and repeatable; it is not a
production migration.

## Change procedure

1. Change the SQLAlchemy model and add an Alembic revision.
2. Review generated SQL, foreign-key deletion behavior, uniqueness, nullability,
   and indexes for the actual query path.
3. Test upgrade from the previous deployed revision against a disposable copy.
4. Back up before production migration and rehearse restore/rollback.
5. Deploy backward-compatible application code before destructive schema work.

Never edit an applied revision, create tables with `Base.metadata.create_all` in
production, store uploaded binaries in rows, or place database credentials in a
frontend environment variable.

## Production requirements

- encrypted connections and secrets supplied by the platform;
- least-privilege migration and runtime roles;
- encrypted backups with point-in-time recovery and regularly proven restores;
- connection-pool sizing aligned with API/worker replica counts;
- slow-query monitoring and evidence-driven indexes;
- retention/lifecycle policies coordinated with object storage and audit rules.

Row-level security remains a defense-in-depth option for real citizen data. The
current application authorization is tested, but RLS policy design requires the
production identity and jurisdiction model and should not be guessed in a demo
schema.
