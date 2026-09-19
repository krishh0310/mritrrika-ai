#!/usr/bin/env python
"""Issue, list and revoke API keys for other government systems.

    python scripts/api_keys.py create --user state-lrms@mrittika.demo --name "UP LRMS"
    python scripts/api_keys.py list
    python scripts/api_keys.py revoke <prefix>

A key acts as its user -- a service account with the roles and jurisdiction
that system should have. The key is printed once and only its hash is stored.
Callers send it as `X-API-Key: <key>`.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.auth.dependencies import hash_api_key  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ApiKey, User  # noqa: E402
from app.services import audit_service  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--user", required=True, help="email of the service user")
    create.add_argument("--name", required=True, help="which system holds the key")
    commands.add_parser("list")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("prefix")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.command == "create":
            user = session.execute(select(User).where(User.email == args.user)).scalar_one_or_none()
            if user is None:
                raise SystemExit(f"no user {args.user}")
            key = "mk_" + secrets.token_urlsafe(32)
            row = ApiKey(name=args.name, prefix=key[:11], key_hash=hash_api_key(key),
                         user_id=user.id)
            session.add(row)
            session.flush()
            audit_service.record(session, action="api_key.created", entity_type="api_key",
                                 entity_id=row.prefix,
                                 after_state={"name": args.name, "user": args.user})
            session.commit()
            print(f"{key}\n\nShown once. Send it as X-API-Key. Acts as {args.user}.")
        elif args.command == "list":
            for row, email in session.execute(
                select(ApiKey, User.email).join(User, User.id == ApiKey.user_id)
            ).all():
                state = "revoked" if row.revoked_at else "active"
                print(f"{row.prefix}  {state:8s} {row.name}  ({email})  "
                      f"last used {row.last_used_at}")
        else:
            rows = session.execute(
                select(ApiKey).where(ApiKey.prefix == args.prefix, ApiKey.revoked_at.is_(None))
            ).scalars().all()
            if not rows:
                raise SystemExit(f"no active key with prefix {args.prefix}")
            for row in rows:
                row.revoked_at = datetime.now(UTC)
                audit_service.record(session, action="api_key.revoked", entity_type="api_key",
                                     entity_id=row.prefix)
            session.commit()
            print(f"revoked {len(rows)} key(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
