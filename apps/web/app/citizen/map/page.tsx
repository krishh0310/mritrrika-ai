"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { MapPin, Sparkles, X } from "lucide-react";

import { OwnershipTimeline } from "@/components/shared/ownership-timeline";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useMyParcels, useOwnershipHistory, useVillageParcels } from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, LoadingState, Select, SyntheticNotice,
} from "@mrittika/ui";

// MapLibre touches `window` at import time, so it cannot be server-rendered.
const ParcelMap = dynamic(
  () => import("@/components/shared/parcel-map").then((m) => m.ParcelMap),
  { ssr: false, loading: () => <LoadingState label="the map" /> },
);

/**
 * §16 — the citizen's parcels on the cadastre.
 *
 * Clicking a parcel opens a side panel with only what §16 permits: khasra,
 * village, area, classification, share, status and latest mutation. Nothing
 * about confidence or verification appears here.
 */
function CitizenMapScreen() {
  const requested = useSearchParams().get("parcel");

  const parcels = useMyParcels();
  const holdings = useMemo(() => parcels.data?.parcels ?? [], [parcels.data]);

  const villages = useMemo(() => {
    const seen = new Map<string, string>();
    for (const holding of holdings) {
      if (holding.village_id) seen.set(holding.village_id, holding.village ?? holding.village_id);
    }
    return [...seen.entries()];
  }, [holdings]);

  const [chosenVillageId, setChosenVillageId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(requested);

  // Default to the village of the requested parcel, or the first one held.
  const requestedVillageId = requested
    ? holdings.find((holding) => holding.parcel_id === requested)?.village_id
    : null;
  const villageId = chosenVillageId ?? requestedVillageId ?? villages[0]?.[0] ?? null;

  const geo = useVillageParcels(villageId);
  const mine = useMemo(() => holdings.map((h) => h.parcel_id), [holdings]);
  const selectedHolding = holdings.find((h) => h.parcel_id === selected);
  const history = useOwnershipHistory(selectedHolding ? selected : null);

  return (
    <>
      <PageHeader
        title="Parcel map"
        description="Your parcels are filled in orange; the rest of the village is drawn for context."
        actions={
          villages.length > 1 ? (
            <Select
              value={villageId ?? ""}
              onChange={(e) => setChosenVillageId(e.target.value)}
              className="w-48"
              aria-label="Village"
            >
              {villages.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </Select>
          ) : null
        }
      />

      <QueryBoundary
        query={parcels}
        label="your parcels"
        empty={{
          when: (data) => data.parcels.length === 0,
          node: (
            <Card>
              <EmptyState
                icon={<MapPin className="size-7" aria-hidden />}
                title="No parcels to show"
                description="Once a record naming you is approved, its parcel appears here."
              />
            </Card>
          ),
        }}
      >
        {() => (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="h-[32rem] lg:h-[38rem]">
              {geo.isPending && villageId ? (
                <Card className="flex h-full items-center justify-center">
                  <LoadingState label="the cadastre" />
                </Card>
              ) : geo.isError ? (
                <Card className="flex h-full items-center justify-center">
                  <EmptyState
                    title="The cadastre could not be loaded"
                    description="The parcel geometry for this village is unavailable right now."
                  />
                </Card>
              ) : (
                <ParcelMap
                  parcels={geo.data}
                  highlight={mine}
                  selected={selected}
                  onSelect={setSelected}
                />
              )}
            </div>

            <Card className="self-start">
              {selectedHolding ? (
                <>
                  <CardHeader
                    title={`Khasra ${selectedHolding.khasra_number}`}
                    description={
                      <span className="id text-xs">{selectedHolding.parcel_id}</span>
                    }
                    action={
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setSelected(null)}
                        aria-label="Close panel"
                      >
                        <X aria-hidden />
                      </Button>
                    }
                  />
                  <dl className="grid grid-cols-2 gap-4 p-5 text-sm">
                    {[
                      ["Village", selectedHolding.village ?? "—", "record-text"],
                      [
                        "Area",
                        `${selectedHolding.area_value} ${selectedHolding.area_unit_raw ?? selectedHolding.area_unit}`,
                        "record-text",
                      ],
                      ["Classification", selectedHolding.land_class ?? "—", "record-text"],
                      ["Your share", selectedHolding.share ?? "—", "id"],
                      ["Held since", selectedHolding.held_since ?? "—", "id"],
                    ].map(([label, value, face]) => (
                      <div key={label}>
                        <dt className="eyebrow">{label}</dt>
                        <dd className={`mt-0.5 text-navy-900 ${face}`}>{value}</dd>
                      </div>
                    ))}
                  </dl>

                  <div className="border-t border-sand-200 p-5">
                    <p className="eyebrow mb-3">Ownership history</p>
                    <QueryBoundary query={history} label="the history">
                      {(data) => <OwnershipTimeline history={data.history} />}
                    </QueryBoundary>
                  </div>

                  <div className="flex flex-wrap gap-2 border-t border-sand-200 p-4">
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/citizen/records/${selectedHolding.parcel_id}`}>
                        Open record
                      </Link>
                    </Button>
                    <Button asChild variant="ghost" size="sm">
                      <Link
                        href={`/citizen/assistant?q=${encodeURIComponent(
                          `Explain the mutation history of khasra ${selectedHolding.khasra_number}.`,
                        )}`}
                      >
                        <Sparkles aria-hidden />
                        Ask AI
                      </Link>
                    </Button>
                  </div>
                </>
              ) : selected ? (
                // A parcel in the village that this citizen does not hold.
                <>
                  <CardHeader title="Not your parcel" />
                  <div className="p-5 text-sm text-sand-700">
                    <p className="id mb-2 text-xs text-sand-500">{selected}</p>
                    <p>
                      This parcel is drawn for context. Details are shown only for
                      parcels recorded against your name.
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-3 -ml-3"
                      onClick={() => setSelected(null)}
                    >
                      Clear selection
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <CardHeader title="Select a parcel" action={<SyntheticNotice />} />
                  <EmptyState
                    icon={<MapPin className="size-7" aria-hidden />}
                    title="Click a parcel on the map"
                    description="Your holdings are the orange ones. Selecting one shows its record and history here."
                  />
                </>
              )}
            </Card>
          </div>
        )}
      </QueryBoundary>
    </>
  );
}

export default function CitizenMapPage() {
  return (
    <Suspense fallback={<LoadingState label="the map" />}>
      <CitizenMapScreen />
    </Suspense>
  );
}
