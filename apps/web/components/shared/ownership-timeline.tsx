"use client";

import { ArrowRight } from "lucide-react";

import type { OwnershipSpan } from "@/lib/queries";
import { EmptyState, cn } from "@mrittika/ui";

/**
 * A parcel's ownership over time (§25, §40).
 *
 * Grouped by the date holdings changed rather than listed span by span. A
 * transfer that hands one parcel to two co-heirs writes two ownership rows on
 * the same date; showing them as two separate events would misrepresent one
 * mutation as two. Each group is one moment in the parcel's history, and the
 * mutation that caused it labels the arrow into it.
 */

type Era = {
  from: string;
  holders: OwnershipSpan[];
  mutationNumber: string | null;
  mutationType: string | null;
};

function groupIntoEras(history: OwnershipSpan[]): Era[] {
  const byDate = new Map<string, Era>();

  for (const span of history) {
    const existing = byDate.get(span.valid_from);
    if (existing) {
      existing.holders.push(span);
      // A mutation number on any row of the group explains the whole group.
      existing.mutationNumber ??= span.mutation_number;
      existing.mutationType ??= span.mutation_type;
    } else {
      byDate.set(span.valid_from, {
        from: span.valid_from,
        holders: [span],
        mutationNumber: span.mutation_number,
        mutationType: span.mutation_type,
      });
    }
  }

  return [...byDate.values()].sort((a, b) => a.from.localeCompare(b.from));
}

function year(iso: string) {
  return iso.slice(0, 4);
}

export function OwnershipTimeline({
  history,
  className,
}: {
  history: OwnershipSpan[];
  className?: string;
}) {
  if (history.length === 0) {
    return (
      <EmptyState
        title="No ownership history recorded"
        description="This parcel has no approved ownership records on file yet."
      />
    );
  }

  const eras = groupIntoEras(history);

  return (
    <ol className={cn("relative", className)}>
      {eras.map((era, index) => {
        const current = era.holders.some((h) => h.valid_to === null);
        return (
          <li key={era.from} className="relative flex gap-4 pb-6 last:pb-0">
            {/* The spine. Stops at the last entry rather than trailing off. */}
            {index < eras.length - 1 ? (
              <span
                aria-hidden
                className="absolute top-7 bottom-0 left-[1.4375rem] w-px bg-sand-200"
              />
            ) : null}

            <div
              className={cn(
                "id relative z-10 flex size-12 shrink-0 items-center justify-center rounded-full",
                "border text-xs font-semibold",
                current
                  ? "border-burnt bg-cream text-burnt"
                  : "border-sand-200 bg-white text-sand-700",
              )}
            >
              {year(era.from)}
            </div>

            <div className="min-w-0 flex-1 pt-1">
              {era.mutationNumber ? (
                <p className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-sand-500">
                  <ArrowRight className="size-3" aria-hidden />
                  Mutation <span className="id">{era.mutationNumber}</span>
                  {era.mutationType ? (
                    <span className="rounded-chip bg-sand-100 px-1.5 py-0.5 text-[0.6875rem] font-medium tracking-wide text-sand-700 uppercase">
                      {era.mutationType.replaceAll("_", " ")}
                    </span>
                  ) : null}
                </p>
              ) : (
                <p className="mb-1 text-xs text-sand-500">Earliest record on file</p>
              )}

              <ul className="space-y-1">
                {era.holders.map((holder) => (
                  <li
                    key={`${holder.owner_id}-${holder.valid_from}`}
                    className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5"
                  >
                    <span className="record-text text-[0.9375rem] font-medium text-navy-900">
                      {holder.owner}
                    </span>
                    <span className="id text-xs text-sand-700">{holder.share}</span>
                    <span className="text-xs text-sand-500">
                      {holder.valid_to
                        ? `until ${holder.valid_to}`
                        : "current holder"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
