"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { MapPin } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useAnomalies, useLocations, useVillageParcels } from "@/lib/queries";
import {
  Card, CardHeader, EmptyState, LoadingState, Select, SyntheticNotice,
} from "@mrittika/ui";

const ParcelMap = dynamic(
  () => import("@/components/shared/parcel-map").then((m) => m.ParcelMap),
  { ssr: false, loading: () => <LoadingState label="the map" /> },
);

/**
 * §31 map overview.
 *
 * The highlight here means something different from the citizen's map: these
 * are the parcels carrying an open flag, so an administrator can see whether
 * inconsistencies cluster in one part of a village.
 */
export default function TehsildarMapPage() {
  const villages = useLocations("VILLAGE");
  const anomalies = useAnomalies("OPEN");
  const [chosenVillageId, setChosenVillageId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const options = useMemo(
    () => villages.data?.locations ?? [],
    [villages.data],
  );
  const villageId = chosenVillageId ?? options[0]?.location_id ?? null;

  const geo = useVillageParcels(villageId);

  const flagged = useMemo(
    () =>
      (anomalies.data?.flags ?? [])
        .map((f) => f.parcel_id)
        .filter((id): id is string => Boolean(id)),
    [anomalies.data],
  );

  const selectedFlags = (anomalies.data?.flags ?? []).filter(
    (f) => f.parcel_id === selected,
  );

  return (
    <>
      <PageHeader
        title="Cadastre"
        description="Parcels carrying an open flag are filled; the rest of the village is context."
        actions={
          <div className="flex items-center gap-2">
            <SyntheticNotice className="self-center" />
            <Select
              value={villageId ?? ""}
              onChange={(e) => setChosenVillageId(e.target.value)}
              className="w-48"
              aria-label="Village"
            >
              {options.map((location) => (
                <option key={location.location_id} value={location.location_id}>
                  {location.name_devanagari ?? location.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="h-[32rem] lg:h-[38rem]">
          <QueryBoundary query={geo} label="the cadastre">
            {(data) => (
              <ParcelMap
                parcels={data}
                highlight={flagged}
                selected={selected}
                onSelect={setSelected}
              />
            )}
          </QueryBoundary>
        </div>

        <Card className="self-start">
          <CardHeader title={selected ? "Selected parcel" : "Open flags"} />
          {selected ? (
            <div className="p-5">
              <p className="id mb-3 text-xs text-sand-500">{selected}</p>
              {selectedFlags.length === 0 ? (
                <p className="text-sm text-sand-700">
                  Nothing is flagged on this parcel.
                </p>
              ) : (
                <ul className="space-y-3">
                  {selectedFlags.map((flag) => (
                    <li key={flag.flag_id}>
                      <p className="text-sm font-medium text-navy-900">
                        {flag.anomaly_type.replaceAll("_", " ").toLowerCase()}
                      </p>
                      <p className="mt-0.5 text-sm text-sand-700">
                        {flag.explanation}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <QueryBoundary
              query={anomalies}
              label="the flags"
              empty={{
                when: (data) => data.flags.length === 0,
                node: (
                  <EmptyState
                    icon={<MapPin className="size-7" aria-hidden />}
                    title="Nothing flagged"
                    description="No parcel in the cadastre currently shows a questionable pattern."
                  />
                ),
              }}
            >
              {(data) => (
                <ul className="divide-y divide-sand-100">
                  {data.flags.map((flag) => (
                    <li key={flag.flag_id} className="px-5 py-3">
                      <button
                        type="button"
                        onClick={() => setSelected(flag.parcel_id)}
                        className="text-left"
                      >
                        <p className="text-sm font-medium text-navy-900">
                          {flag.khasra_number
                            ? `Khasra ${flag.khasra_number}`
                            : flag.parcel_id}
                        </p>
                        <p className="mt-0.5 text-xs text-sand-500">
                          {flag.anomaly_type.replaceAll("_", " ").toLowerCase()}
                        </p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </QueryBoundary>
          )}
        </Card>
      </div>
    </>
  );
}
