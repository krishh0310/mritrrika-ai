#!/usr/bin/env python
"""Seed the database from the generated synthetic world (Stage 2, step 8).

    python scripts/seed_demo.py --profile slice1

IDEMPOTENT BY DESIGN. Every row is matched on its stable external_id and
updated in place, so running this repeatedly converges rather than duplicating.
That matters because the demo is re-seeded often and a duplicated ownership row
would silently break the "shares sum to 1" invariant.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    CitizenProfile,
    LandRecord,
    Location,
    ModelVersion,
    Mutation,
    Owner,
    OwnershipRecord,
    Parcel,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.security.passwords import hash_password  # noqa: E402
from mrittika_domain import SyntheticWorld  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

#: §36 capabilities, granted per role. Enforced server-side; the frontend never
#: decides any of this.
PERMISSIONS: dict[str, list[str]] = {
    "CITIZEN": [
        "record:search_public", "parcel:view_own", "record:view_own",
        "grievance:create", "grievance:view_own", "ai:query", "gis:view",
    ],
    "DEO": [
        "record:search_public", "document:upload", "document:enter_metadata",
        "document:start_processing", "ocr:view", "confidence:view",
        "gis:view", "ai:query",
    ],
    "VERIFIER": [
        "record:search_public", "ocr:view", "confidence:view",
        "extraction:correct", "document:verify", "document:return",
        "anomaly:view", "gis:view", "ai:query", "audit:view_limited",
        "grievance:review_limited",
    ],
    "TEHSILDAR": [
        "record:search_public", "ocr:view", "confidence:view",
        "document:approve", "document:reject", "document:return",
        "anomaly:view", "gis:view", "ai:query", "audit:view_full",
        "grievance:review", "analytics:view", "integration:sync", "gis:features",
        "integration:status",
    ],
    # Read-only stakeholders. Nothing here changes a record; each sees only
    # its own jurisdiction (the state, the whole country, or a district).
    "STATE_OFFICER": [
        "record:search_public", "gis:view", "analytics:view", "anomaly:view",
        "audit:view_full", "gis:features", "integration:status",
    ],
    "CENTRAL_OFFICER": [
        "record:search_public", "gis:view", "analytics:view", "anomaly:view",
        "gis:features", "integration:status",
    ],
    # The survey department's concern is the cadastre: the map, and where the
    # records and the geometry disagree.
    "SURVEYOR": [
        "record:search_public", "gis:view", "anomaly:view", "gis:features",
    ],
    # Aggregates and an anonymised export -- never names, never a parcel id.
    "RESEARCHER": [
        "analytics:view", "research:export",
    ],
    # A state LRMS calling in with an API key: read records, pull and push
    # Records of Rights. It cannot touch the workflow.
    "INTEGRATION": [
        "record:search_public", "gis:view", "integration:sync",
    ],
}

#: The registry is the single source of truth (§64). This used to be a
#: hard-coded copy that had drifted from it -- and named PP-Structure and
#: IndicBERT, neither of which was ever integrated (§69).
MODEL_REGISTRY = REPO_ROOT / "models" / "registry" / "model_versions.json"


def load_model_versions() -> list[dict]:
    return json.loads(MODEL_REGISTRY.read_text())["versions"]


def upsert(session: Session, model, external_id: str, **values):
    """Fetch-or-create by external_id, then apply `values`."""
    stmt = select(model).where(model.external_id == external_id)
    instance = session.execute(stmt).scalar_one_or_none()
    if instance is None:
        instance = model(external_id=external_id, **values)
        session.add(instance)
    else:
        for key, value in values.items():
            setattr(instance, key, value)
    return instance


def seed_roles_and_permissions(session: Session) -> dict[str, Role]:
    permissions: dict[str, Permission] = {}
    for codes in PERMISSIONS.values():
        for code in codes:
            if code in permissions:
                continue
            existing = session.execute(
                select(Permission).where(Permission.code == code)
            ).scalar_one_or_none()
            if existing is None:
                existing = Permission(code=code)
                session.add(existing)
            permissions[code] = existing
    session.flush()

    roles: dict[str, Role] = {}
    for role_code, codes in PERMISSIONS.items():
        role = session.execute(
            select(Role).where(Role.code == role_code)
        ).scalar_one_or_none()
        if role is None:
            role = Role(code=role_code, description=f"{role_code} role")
            session.add(role)
            session.flush()
        roles[role_code] = role

        existing_links = {
            rp.permission_id
            for rp in session.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).scalars()
        }
        for code in codes:
            pid = permissions[code].id
            if pid not in existing_links:
                session.add(RolePermission(role_id=role.id, permission_id=pid))
    session.flush()
    return roles


def seed(session: Session, world: SyntheticWorld, password: str) -> dict[str, int]:
    roles = seed_roles_and_permissions(session)

    for entry in load_model_versions():
        row = session.execute(
            select(ModelVersion).where(ModelVersion.code == entry["name"])
        ).scalar_one_or_none()
        if row is None:
            row = ModelVersion(code=entry["name"])
            session.add(row)
        # Update, not insert-if-missing: otherwise correcting the registry
        # never reaches a database that was seeded with the old wording.
        row.kind = entry["kind"]
        row.provider = entry["provider"]
        row.description = f"{entry['description']} {entry['notes']}".strip()
    session.flush()

    # Locations, parents first so parent_id always resolves.
    location_ids: dict[str, str] = {}
    for level in ("COUNTRY", "STATE", "DISTRICT", "TEHSIL", "VILLAGE"):
        for loc in (x for x in world.locations if x.level == level):
            row = upsert(
                session, Location, loc.location_id,
                name=loc.name,
                name_devanagari=loc.name_devanagari,
                level=loc.level,
                parent_id=location_ids.get(loc.parent_id) if loc.parent_id else None,
            )
            session.flush()
            location_ids[loc.location_id] = row.id

    owner_ids: dict[str, str] = {}
    for owner in world.owners:
        row = upsert(
            session, Owner, owner.owner_id,
            name=owner.name, guardian_name=owner.guardian_name,
            is_synthetic=owner.is_synthetic,
        )
        session.flush()
        owner_ids[owner.owner_id] = row.id

    parcel_ids: dict[str, str] = {}
    for parcel in world.parcels:
        row = upsert(
            session, Parcel, parcel.parcel_id,
            village_id=location_ids[parcel.village_id],
            khasra_number=parcel.khasra_number,
            khata_number=parcel.khata_number,
            area_value=parcel.area_value,
            area_unit=parcel.area_unit.value,
            area_unit_raw=parcel.area_unit_raw,
            land_class=parcel.land_class,
            geometry=(
                f"SRID=4326;{parcel.geometry_wkt}" if parcel.geometry_wkt else None
            ),
            is_synthetic=parcel.is_synthetic,
        )
        session.flush()
        parcel_ids[parcel.parcel_id] = row.id

    # Mutations before ownership, because ownership references mutation_id.
    mutation_ids: dict[str, str] = {}
    for mutation in world.mutations:
        row = upsert(
            session, Mutation, mutation.mutation_id,
            parcel_id=parcel_ids[mutation.parcel_id],
            mutation_number=mutation.mutation_number,
            mutation_type=mutation.mutation_type.value,
            effective_date=mutation.effective_date,
            registration_date=mutation.registration_date,
            status=mutation.status,
        )
        session.flush()
        mutation_ids[mutation.mutation_id] = row.id

    for record in world.ownership:
        upsert(
            session, OwnershipRecord, record.ownership_id,
            owner_id=owner_ids[record.owner_id],
            parcel_id=parcel_ids[record.parcel_id],
            mutation_id=mutation_ids.get(record.mutation_id) if record.mutation_id else None,
            share=record.share,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            status=record.status,
        )

    # A world is the whole truth about its parcels. Upserting alone left rows
    # from a previously seeded profile in place: slice1 and v1 share parcel ids
    # but not histories, so PARCEL-UP-DEMO-0181 ended up with two ACTIVE holders.
    seeded = list(parcel_ids.values())
    session.execute(delete(OwnershipRecord).where(
        OwnershipRecord.parcel_id.in_(seeded),
        OwnershipRecord.external_id.not_in([r.ownership_id for r in world.ownership]),
    ))
    session.execute(delete(Mutation).where(
        Mutation.parcel_id.in_(seeded),
        Mutation.external_id.not_in([m.mutation_id for m in world.mutations]),
    ))

    for record in world.land_records:
        upsert(
            session, LandRecord, record.record_id,
            parcel_id=parcel_ids[record.parcel_id],
            document_type=record.document_type.value,
            record_year=record.record_year,
            status="APPROVED",
            is_synthetic=record.is_synthetic,
        )
    session.flush()

    # Users last -- citizen profiles need owners to exist.
    for user in world.users:
        row = upsert(
            session, User, user.user_id,
            email=user.email,
            full_name=user.name,
            jurisdiction_id=(
                location_ids.get(user.jurisdiction_id) if user.jurisdiction_id else None
            ),
            is_active=True,
        )
        # Only set the hash on creation: re-hashing every seed would churn the
        # column for no reason and make "did the seed change anything?" noisy.
        if not row.password_hash:
            row.password_hash = hash_password(password)
        session.flush()

        role = roles[user.role.value]
        has_role = session.execute(
            select(UserRole).where(
                UserRole.user_id == row.id, UserRole.role_id == role.id
            )
        ).scalar_one_or_none()
        if has_role is None:
            session.add(UserRole(user_id=row.id, role_id=role.id))

        if user.owner_id:
            profile = session.execute(
                select(CitizenProfile).where(CitizenProfile.user_id == row.id)
            ).scalar_one_or_none()
            if profile is None:
                session.add(
                    CitizenProfile(user_id=row.id, owner_id=owner_ids[user.owner_id])
                )
            else:
                profile.owner_id = owner_ids[user.owner_id]

    session.commit()

    return {
        "locations": session.scalar(select(func.count()).select_from(Location)),
        "owners": session.scalar(select(func.count()).select_from(Owner)),
        "parcels": session.scalar(select(func.count()).select_from(Parcel)),
        "ownership": session.scalar(select(func.count()).select_from(OwnershipRecord)),
        "mutations": session.scalar(select(func.count()).select_from(Mutation)),
        "land_records": session.scalar(select(func.count()).select_from(LandRecord)),
        "users": session.scalar(select(func.count()).select_from(User)),
        "roles": session.scalar(select(func.count()).select_from(Role)),
        "permissions": session.scalar(select(func.count()).select_from(Permission)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="slice1")
    args = parser.parse_args()

    world_path = REPO_ROOT / "datasets" / "metadata" / f"world.{args.profile}.json"
    if not world_path.exists():
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "generate_dataset.py"),
             "--profile", args.profile],
            check=True,
        )

    world = SyntheticWorld.model_validate_json(world_path.read_text())
    import os
    password = os.environ.get("DEMO_PASSWORD", "demo_change_me")

    with SessionLocal() as session:
        counts = seed(session, world, password)
        from app.services.embedding_service import reindex_approved

        counts["embeddings"] = reindex_approved(session)

    print("seeded:")
    for key, value in counts.items():
        print(f"  {key:14s} {value}")
    print("\ndemo logins (password from DEMO_PASSWORD):")
    for user in world.users:
        print(f"  {user.role.value:10s} {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
