# infrastructure

- `docker/`: Dockerfiles (api, worker, web, postgres) and compose overlays (`compose.full.yml`, `compose.monitoring.yml`, `compose.geoserver.yml`)
- `monitoring/`: Prometheus and Grafana config. `monitoring/secrets/` is gitignored and holds the scrape token.
- `geoserver/`: read-only database role for pg_featureserv

The root `docker-compose.yml` brings up only the local-dev backing services.
