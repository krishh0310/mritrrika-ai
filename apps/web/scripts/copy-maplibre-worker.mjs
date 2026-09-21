// MapLibre 6 finds its web worker at ./maplibre-gl-worker.mjs next to its own
// module. Once Next bundles MapLibre into a chunk, that path 404s, the worker
// never starts, and the map draws no parcels -- silently. So the worker (and
// the shared module it imports) are served from public/, copied from the
// installed package so they always match its version. Runs before dev/build.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(createRequire(import.meta.url).resolve("maplibre-gl/package.json")), "dist");
const target = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "maplibre");
mkdirSync(target, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(dist, file), join(target, file));
}
