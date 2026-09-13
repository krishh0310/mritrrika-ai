#!/usr/bin/env python
"""Configure GeoServer to publish the approved cadastre (§11).

    docker compose -f docker-compose.yml \
                   -f infrastructure/docker/compose.geoserver.yml up -d
    psql ... -f infrastructure/geoserver/reader-role.sql   # once
    python scripts/provision_geoserver.py

Creates a workspace, a PostGIS store pointing at the READ-ONLY role, and one
feature type over `gis_published_parcels`. Idempotent: re-running updates
rather than duplicating, so it is safe from a deploy script.

It refuses to point the store at a superuser account. GeoServer serves whatever
its store can read, so the credentials ARE the authorization boundary -- a
store configured with the application's own database user would publish every
owner name over WFS the moment somebody added a layer in the admin UI.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin

import httpx

WORKSPACE = "mrittika"
STORE = "mrittika_cadastre"
LAYER = "gis_published_parcels"
SRS = "EPSG:4326"

#: Accounts that must never back a published store.
FORBIDDEN_DB_USERS = {"postgres", "mrittika", "root", "admin"}


def api(client: httpx.Client, base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/rest/", path.lstrip("/"))


def put_or_post(client, base, collection_path, item_path, payload, label) -> None:
    """Create the object, or update it if it already exists."""
    existing = client.get(api(client, base, item_path))
    if existing.status_code == 200:
        response = client.put(api(client, base, item_path), json=payload)
        action = "updated"
    else:
        response = client.post(api(client, base, collection_path), json=payload)
        action = "created"

    if response.status_code >= 300:
        raise SystemExit(
            f"{label}: {action} failed with {response.status_code}\n{response.text}"
        )
    print(f"  {label}: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get(
        "GEOSERVER_URL", "http://127.0.0.1:8600/geoserver"))
    parser.add_argument("--user", default=os.environ.get("GEOSERVER_ADMIN_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("GEOSERVER_ADMIN_PASSWORD"))
    parser.add_argument("--db-host", default=os.environ.get("GEOSERVER_DB_HOST", "postgres"))
    parser.add_argument("--db-port", default=os.environ.get("GEOSERVER_DB_PORT", "5432"))
    parser.add_argument("--db-name", default=os.environ.get("POSTGRES_DB", "mrittika"))
    parser.add_argument("--db-user", default=os.environ.get(
        "GEOSERVER_DB_USER", "geoserver_reader"))
    parser.add_argument("--db-password", default=os.environ.get("GEOSERVER_DB_PASSWORD"))
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("set GEOSERVER_ADMIN_PASSWORD (or pass --password)")
    if not args.db_password:
        raise SystemExit("set GEOSERVER_DB_PASSWORD (or pass --db-password)")
    if args.db_user in FORBIDDEN_DB_USERS:
        raise SystemExit(
            f"refusing to publish through '{args.db_user}'. GeoServer serves "
            "whatever its store can read, so the store's credentials are the "
            "authorization boundary. Use geoserver_reader -- see "
            "infrastructure/geoserver/reader-role.sql."
        )

    client = httpx.Client(auth=(args.user, args.password), timeout=30.0)

    try:
        probe = client.get(api(client, args.url, "about/version.json"))
    except httpx.HTTPError as exc:
        raise SystemExit(f"cannot reach GeoServer at {args.url}: {exc}") from None
    if probe.status_code == 401:
        raise SystemExit("GeoServer rejected the admin credentials")
    probe.raise_for_status()
    print(f"GeoServer reachable at {args.url}")

    put_or_post(
        client, args.url,
        "workspaces", f"workspaces/{WORKSPACE}.json",
        {"workspace": {"name": WORKSPACE}},
        f"workspace '{WORKSPACE}'",
    )

    put_or_post(
        client, args.url,
        f"workspaces/{WORKSPACE}/datastores",
        f"workspaces/{WORKSPACE}/datastores/{STORE}.json",
        {"dataStore": {
            "name": STORE,
            "connectionParameters": {"entry": [
                {"@key": "dbtype", "$": "postgis"},
                {"@key": "host", "$": args.db_host},
                {"@key": "port", "$": str(args.db_port)},
                {"@key": "database", "$": args.db_name},
                {"@key": "user", "$": args.db_user},
                {"@key": "passwd", "$": args.db_password},
                {"@key": "schema", "$": "public"},
                {"@key": "Expose primary keys", "$": "true"},
            ]},
        }},
        f"store '{STORE}'",
    )

    put_or_post(
        client, args.url,
        f"workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes",
        f"workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{LAYER}.json",
        {"featureType": {
            "name": LAYER,
            "nativeName": LAYER,
            "title": "Mrittika AI — approved parcels (synthetic)",
            "abstract": (
                "Approved land parcels from the Mrittika AI prototype. Every "
                "feature is SYNTHETIC demonstration data and describes no "
                "real person's land. Ownership is deliberately not published."
            ),
            "srs": SRS,
            "nativeCRS": SRS,
            "enabled": True,
        }},
        f"layer '{LAYER}'",
    )

    wms = f"{args.url}/{WORKSPACE}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
    wfs = f"{args.url}/{WORKSPACE}/wfs?service=WFS&version=2.0.0&request=GetCapabilities"
    print("\npublished:")
    print(f"  WMS  {wms}")
    print(f"  WFS  {wfs}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
