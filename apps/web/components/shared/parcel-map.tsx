"use client";

import maplibregl, { type Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { ParcelFeatureCollection } from "@/lib/queries";
import { cn } from "@mrittika/ui";

import "maplibre-gl/dist/maplibre-gl.css";

/**
 * The cadastral map (§16, §53).
 *
 * No basemap tiles. A synthetic Voronoi cadastre sitting on a real satellite
 * image of Uttar Pradesh would suggest these parcels exist at those
 * coordinates, which §83 forbids — the geometry is generated. So the map draws
 * the parcels on a paper-coloured ground, the way a cadastral sheet is drawn,
 * and it also means the demo needs no tile server and no network.
 *
 * `highlight` is the set of parcels belonging to the signed-in citizen: theirs
 * are filled in burnt orange, the rest of the village is drawn in outline as
 * context (§16 "highlight the citizen's parcels").
 */

export function ParcelMap({
  parcels,
  highlight = [],
  selected,
  onSelect,
  className,
}: {
  parcels: ParcelFeatureCollection | undefined;
  highlight?: string[];
  selected?: string | null;
  onSelect?: (parcelId: string) => void;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);

  // Keep the latest callback without re-registering the map handler, which
  // would otherwise stack a new listener on every parent render.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "ground",
            type: "background",
            paint: { "background-color": "#faf8f3" },
          },
        ],
      },
      center: [80.899, 26.8006],
      zoom: 15,
      attributionControl: false,
    });

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => setReady(true));
    map.current = instance;

    return () => {
      instance.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !parcels?.features?.length) return;

    const data = {
      ...parcels,
      features: parcels.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          // Precomputed so the paint expression stays a simple lookup.
          mine: highlight.includes(String(feature.properties.parcel_id)),
        },
      })),
    };

    const existing = instance.getSource("parcels") as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(data as never);
    } else {
      instance.addSource("parcels", { type: "geojson", data: data as never });

      instance.addLayer({
        id: "parcel-fill",
        type: "fill",
        source: "parcels",
        paint: {
          "fill-color": ["case", ["get", "mine"], "#d2691e", "#ffffff"],
          "fill-opacity": ["case", ["get", "mine"], 0.28, 0.85],
        },
      });

      instance.addLayer({
        id: "parcel-line",
        type: "line",
        source: "parcels",
        paint: {
          "line-color": ["case", ["get", "mine"], "#d2691e", "#cdc5b2"],
          "line-width": ["case", ["get", "mine"], 2, 1],
        },
      });

      instance.addLayer({
        id: "parcel-selected",
        type: "line",
        source: "parcels",
        filter: ["==", ["get", "parcel_id"], ""],
        paint: { "line-color": "#1e3a5f", "line-width": 3 },
      });

      instance.addLayer({
        id: "parcel-label",
        type: "symbol",
        source: "parcels",
        layout: {
          "text-field": ["get", "khasra_number"],
          "text-size": 11,
          "text-allow-overlap": false,
        },
        paint: { "text-color": "#4f4a40", "text-halo-color": "#faf8f3", "text-halo-width": 1.5 },
      });

      instance.on("click", "parcel-fill", (event) => {
        const id = event.features?.[0]?.properties?.parcel_id;
        if (id) onSelectRef.current?.(String(id));
      });
      instance.on("mouseenter", "parcel-fill", () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", "parcel-fill", () => {
        instance.getCanvas().style.cursor = "";
      });
    }

    // Fit to the parcels rather than a hardcoded centre, so a different
    // village still frames correctly.
    const bounds = new maplibregl.LngLatBounds();
    for (const feature of parcels.features) {
      const rings = feature.geometry.coordinates as number[][][];
      for (const ring of rings) {
        for (const [lng, lat] of ring) bounds.extend([lng, lat]);
      }
    }
    if (!bounds.isEmpty()) instance.fitBounds(bounds, { padding: 40, duration: 0 });
  }, [ready, parcels, highlight]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !instance.getLayer("parcel-selected")) return;
    instance.setFilter("parcel-selected", ["==", ["get", "parcel_id"], selected ?? ""]);
  }, [ready, selected]);

  return (
    <div
      ref={container}
      className={cn("h-full w-full rounded-card border border-sand-200 bg-sand-50", className)}
      role="application"
      aria-label="Cadastral parcel map"
    />
  );
}
