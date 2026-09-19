"use client";

import { useState } from "react";

import type { LocationProgress, ProgressStage } from "@/lib/queries";
import { cn, Table, Td, Th } from "@mrittika/ui";

import { NAVY } from "./charts";

const LEVEL_LABEL: Record<LocationProgress["level"], string> = {
  COUNTRY: "Country",
  STATE: "State",
  DISTRICT: "District",
  TEHSIL: "Tehsil",
  VILLAGE: "Village",
};

/** The pipeline stages behind the headline, in the order work moves. */
const STAGE_LABEL: Record<Exclude<ProgressStage, "approved">, string> = {
  awaiting_approval: "awaiting approval",
  in_verification: "in verification",
  in_processing: "processing",
  needs_attention: "needs attention",
};

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/**
 * One bar, one measure: the approved share. A single hue on a sand track,
 * with the number printed beside it — the colour never carries the value.
 */
function ProgressBar({ value, label }: { value: number | null; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className="h-2 w-28 shrink-0 overflow-hidden rounded-[2px] bg-sand-100"
        role="img"
        aria-label={`${label}: ${percent(value)}`}
      >
        <div
          className="h-full rounded-[2px]"
          style={{ width: `${(value ?? 0) * 100}%`, background: NAVY }}
        />
      </div>
      <span className="id w-10 text-right text-sm text-sand-700">{percent(value)}</span>
    </div>
  );
}

/**
 * §31 digitization progress, level by level.
 *
 * The API returns every location in the officer's jurisdiction, each rolled up
 * from its villages, so switching level is a filter here rather than a new
 * request. The opening level is the first with more than one place in it —
 * a district officer's single district row is a headline, not a comparison.
 */
export function ProgressByLocation({
  levels,
  rows,
}: {
  levels: LocationProgress["level"][];
  rows: LocationProgress[];
}) {
  const opening =
    levels.find((level) => rows.filter((r) => r.level === level).length > 1) ??
    levels[levels.length - 1];
  const [level, setLevel] = useState(opening);

  if (rows.length === 0) {
    return (
      <p className="px-5 py-8 text-center text-sm text-sand-500">
        No locations in your jurisdiction yet.
      </p>
    );
  }

  const shown = rows
    .filter((row) => row.level === level)
    .sort((a, b) => b.documents - a.documents || a.name.localeCompare(b.name));

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 border-b border-sand-100 px-5 py-3" role="tablist">
        {levels.map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={option === level}
            onClick={() => setLevel(option)}
            className={cn(
              "rounded-chip px-3 py-1 text-xs font-medium transition-colors",
              option === level
                ? "bg-navy-800 text-white"
                : "text-navy-800 hover:bg-navy-100/60",
            )}
          >
            {LEVEL_LABEL[option]}-wise
          </button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <Table>
          <thead>
            <tr>
              <Th>{LEVEL_LABEL[level]}</Th>
              <Th className="text-right">Documents</Th>
              <Th>Approved</Th>
              <Th>Parcels digitized</Th>
              <Th>Still in the pipeline</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const pipeline = (Object.keys(STAGE_LABEL) as (keyof typeof STAGE_LABEL)[])
                .filter((stage) => row[stage] > 0)
                .map((stage) => `${row[stage]} ${STAGE_LABEL[stage]}`);
              return (
                <tr key={row.location_id} className="hover:bg-sand-50">
                  <Td>
                    <span className="text-sm font-medium text-navy-900">{row.name}</span>
                    {row.name_local ? (
                      <span className="ml-2 text-xs text-sand-500">{row.name_local}</span>
                    ) : null}
                  </Td>
                  <Td className="id text-right text-sand-700">{row.documents}</Td>
                  <Td>
                    <ProgressBar value={row.progress} label={`${row.name} approved`} />
                  </Td>
                  <Td>
                    <ProgressBar
                      value={row.parcel_coverage}
                      label={`${row.name} parcels digitized`}
                    />
                    <span className="id mt-0.5 block text-xs text-sand-500">
                      {row.parcels_digitized} of {row.parcels}
                    </span>
                  </Td>
                  <Td className="text-xs text-sand-700">
                    {pipeline.length ? pipeline.join(" · ") : "—"}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </div>
      <p className="border-t border-sand-100 px-5 py-3 text-xs text-sand-500">
        <strong className="font-medium text-sand-700">Approved</strong> is the share of
        uploaded documents approved.{" "}
        <strong className="font-medium text-sand-700">Parcels digitized</strong> is the
        share of parcels with at least one approved record — how much of the land is done.
      </p>
    </div>
  );
}
