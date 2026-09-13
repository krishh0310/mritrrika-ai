# Publishing the cadastre to external systems

The parcels this system approves are useful to other government systems — a
revenue portal, a BhuNaksha-style viewer, a planning department's desktop GIS.
Those systems speak WMS and WFS, not this application's REST API, so GeoServer
sits in front of PostGIS and serves the standard protocols.

Everything below follows from one fact.

## GeoServer has no idea who is asking

It cannot evaluate `gis:view`. It cannot scope to a tehsildar's jurisdiction.
It has no principal at all. It serves whatever its database role can read, to
whoever reaches its port, and the OGC protocols make that generous by design —
`WFS GetFeature` with `outputFormat=csv` will hand over the entire attribute
table of any layer it can see.

So the protection is not in GeoServer's configuration, which an admin can
change in a web UI. It is in two places that cannot be changed by accident:

**1. The view.** GeoServer is pointed at `gis_published_parcels`, never at
`parcels`. Created in migration `b2c3d4e5f6a7`:

* **Approved records only** — a parcel with no `APPROVED` land record does not
  appear, the same rule §17 applies to citizen search.
* **No ownership** — not a redacted column, no owner join at all. There is no
  query against this view that returns a person's name.
* **No internal AI signals** — no confidence, no anomaly score, no document
  state. §17 keeps those on the officer screens, and a WFS attribute table is
  the widest possible outside.

`tests/backend/test_gis_publication.py` pins the published column set to an
explicit allowlist, so a column reaching the public layer breaks a test before
it reaches a consumer.

**2. The database role.** `geoserver_reader` holds `SELECT` on that one view,
plus the two PostGIS metadata tables a spatial layer cannot load without. It is
not a matter of policy that a WFS request cannot return an owner's name — the
role cannot read the table it would come from:

```
$ psql -U geoserver_reader -d mrittika -c 'SELECT * FROM owners LIMIT 1;'
ERROR:  permission denied for table owners
```

`scripts/provision_geoserver.py` refuses to build a store on `postgres`,
`mrittika`, `root` or `admin` for this reason.

## Standing it up

GeoServer is an **overlay**, not part of the default stack, and its port is
bound to `127.0.0.1`.

```bash
# 1. The view (part of the normal migration chain)
.venv/bin/alembic -c apps/api/alembic.ini upgrade head

# 2. GeoServer
GEOSERVER_ADMIN_PASSWORD='...' docker compose \
  -f docker-compose.yml \
  -f infrastructure/docker/compose.geoserver.yml up -d geoserver

# 3. The read-only role — once, by a human, because it carries a password
docker exec -i mrittika-postgres psql -U mrittika -d mrittika \
  -v pw=the-password < infrastructure/geoserver/reader-role.sql

# 4. Workspace, store and layer (idempotent)
GEOSERVER_ADMIN_PASSWORD='...' GEOSERVER_DB_PASSWORD='the-password' \
  .venv/bin/python scripts/provision_geoserver.py
```

Pass the role password to `psql` **without** surrounding quotes: `:'pw'`
already quotes it, and quoting it twice makes the quotes part of the password —
which then fails as an authentication error rather than as a quoting mistake.

## What it serves

```
WMS  http://127.0.0.1:8600/geoserver/mrittika/wms?service=WMS&version=1.3.0&request=GetCapabilities
WFS  http://127.0.0.1:8600/geoserver/mrittika/wfs?service=WFS&version=2.0.0&request=GetCapabilities
```

Verified working against the seeded cadastre — 160 approved parcels:

```bash
# GeoJSON for a consuming application
curl '.../wfs?service=WFS&version=2.0.0&request=GetFeature\
&typeNames=mrittika:gis_published_parcels&count=2&outputFormat=application/json'
# -> Polygon features; properties carry parcel_id, khasra_number, village_name,
#    area, land_class, and the synthetic-data notice. No owner.

# A rendered tile for a map client
curl -o tile.png '.../wms?service=WMS&version=1.1.1&request=GetMap\
&layers=mrittika:gis_published_parcels&bbox=80.8969,26.7969,80.9035,26.8028\
&width=600&height=600&srs=EPSG:4326&format=image/png'
# -> 512x512+ PNG of the village's parcel boundaries
```

Every feature carries `is_synthetic: true` and
`notice: "DEMO / SYNTHETIC DATA"`. A consuming system that ingests this must
not be able to mistake it for a real cadastre, and the notice travels at the
feature level rather than in documentation nobody reads.

## Before exposing this beyond localhost

The compose file binds to `127.0.0.1` deliberately. Dropping that prefix
publishes the cadastre to every interface on the machine. For any real
deployment:

* Put a reverse proxy with authentication in front of GeoServer. The view keeps
  private data out; it does not make the service public-by-design.
* Change the admin password, and remove `GEOSERVER_ADMIN_USER`/`PASSWORD` from
  the environment afterwards — the upstream image re-applies them on every
  restart and will overwrite roles defined later.
* Rate-limit. An unbounded `GetFeature` over a real state's cadastre is a
  denial-of-service primitive with a URL.
* Keep the `geoserver_reader` password out of version control. It is passed by
  environment variable for exactly this reason.

## What is NOT done

| | status |
|---|---|
| Reverse proxy / authentication in front of GeoServer | not configured — localhost binding only |
| Jurisdiction-scoped layers (one per tehsil) | not implemented; the view is state-wide |
| WFS-T (transactional writes back into PostGIS) | deliberately absent — this is a read-only publication |
| Styling beyond GeoServer's default polygon renderer | not done |
| DILRMP / BhuNaksha / NIC-specific schema mapping | not done — the view is this system's shape, not a national standard |
