"use client";

import Link from "next/link";
import { useState } from "react";
import { LayoutGrid, List, MapPin } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useMyParcels } from "@/lib/queries";
import {
  Button, Card, EmptyState, ParcelCard, Table, Td, Th, cn, RecordText,
} from "@mrittika/ui";

/**
 * §15 — the caller's holdings, as cards or as a table.
 *
 * Both views render the same data from the same query; the toggle is a display
 * preference, not a different request. A citizen comparing five parcels wants
 * the table; one checking a single holding wants the card.
 */
export default function MyLandPage() {
  const parcels = useMyParcels();
  const [view, setView] = useState<"cards" | "table">("cards");

  return (
    <>
      <PageHeader
        title="My land"
        description="Parcels linked to your owner identity. Derived from your session, not from anything this page sends."
        actions={
          <div
            role="group"
            aria-label="View"
            className="inline-flex overflow-hidden rounded-card border border-sand-200 bg-white"
          >
            {(
              [
                ["cards", LayoutGrid, "Cards"],
                ["table", List, "Table"],
              ] as const
            ).map(([mode, Icon, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setView(mode)}
                aria-pressed={view === mode}
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 text-sm",
                  view === mode
                    ? "bg-navy-800 text-white"
                    : "text-navy-800 hover:bg-sand-50",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </button>
            ))}
          </div>
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
                title="Nothing is recorded against your name yet"
                description="Parcels appear here once a tehsildar approves a record naming you as a holder."
                action={
                  <Button asChild variant="outline" size="sm">
                    <Link href="/citizen/search">Search public records</Link>
                  </Button>
                }
              />
            </Card>
          ),
        }}
      >
        {(data) =>
          view === "cards" ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.parcels.map((parcel) => (
                <ParcelCard
                  key={parcel.parcel_id}
                  parcel={parcel}
                  actions={
                    <>
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/citizen/records/${parcel.parcel_id}`}>
                          Open record
                        </Link>
                      </Button>
                      <Button asChild variant="ghost" size="sm">
                        <Link href={`/citizen/map?parcel=${parcel.parcel_id}`}>
                          <MapPin aria-hidden />
                          Map
                        </Link>
                      </Button>
                    </>
                  }
                />
              ))}
            </div>
          ) : (
            <Card>
              <Table>
                <thead>
                  <tr>
                    <Th>Khasra</Th>
                    <Th>Parcel</Th>
                    <Th>Village</Th>
                    <Th>Area</Th>
                    <Th>Share</Th>
                    <Th>Class</Th>
                    <Th>Held since</Th>
                    <Th className="text-right">Record</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.parcels.map((parcel) => (
                    <tr key={parcel.parcel_id} className="hover:bg-sand-50">
                      <Td className="font-medium text-navy-900">
                        <RecordText value={parcel.khasra_number} />
                      </Td>
                      <Td className="id text-sand-700">{parcel.parcel_id}</Td>
                      <Td>
                        <RecordText value={parcel.village} stacked />
                      </Td>
                      <Td>
                        <span className="id">{parcel.area_value}</span>{" "}
                        <RecordText
                          value={parcel.area_unit_raw ?? parcel.area_unit}
                          className="text-sand-700"
                        />
                      </Td>
                      <Td className="id">{parcel.share ?? "—"}</Td>
                      <Td className="text-sand-700">
                        <RecordText value={parcel.land_class} stacked />
                      </Td>
                      <Td className="id text-sand-700">{parcel.held_since ?? "—"}</Td>
                      <Td className="text-right">
                        <Button asChild variant="link" size="sm">
                          <Link href={`/citizen/records/${parcel.parcel_id}`}>Open</Link>
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )
        }
      </QueryBoundary>
    </>
  );
}
