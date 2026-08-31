"use client";

import Link from "next/link";
import { FileText, Landmark, MapPin, MessageSquareWarning, Ruler } from "lucide-react";

import { PageHeader } from "@/components/shell/app-shell";
import { QueryBoundary } from "@/components/shared/query-boundary";
import {
  useCitizenDashboard, useMyGrievances, useMyParcels,
} from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, StatCard, Table, Td, Th,
} from "@mrittika/ui";

/**
 * §14. Every card is a count of something the caller actually holds — derived
 * server-side from their owner identity, never from a parameter this page
 * could send (§62).
 */
export default function CitizenDashboardPage() {
  const summary = useCitizenDashboard();
  const parcels = useMyParcels();
  const grievances = useMyGrievances();

  const holdings = parcels.data?.parcels ?? [];
  const openGrievances = (grievances.data?.grievances ?? []).filter(
    (g) => g.status !== "RESOLVED" && g.status !== "REJECTED",
  ).length;

  return (
    <>
      <PageHeader
        title={
          summary.data ? `Welcome, ${summary.data.citizen_name}` : "Your land"
        }
        description="Everything recorded against your name, as approved by the tehsildar."
        actions={
          <Button asChild variant="outline">
            <Link href="/citizen/my-land">Open my land</Link>
          </Button>
        }
      />

      <QueryBoundary query={summary} label="your summary">
        {(data) => (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="My parcels"
              value={data.parcel_count}
              icon={<Landmark className="size-4" />}
            />
            <StatCard
              label="Total recorded area"
              value={data.total_area}
              hint={data.area_units.join(", ") || "no units recorded"}
              icon={<Ruler className="size-4" />}
            />
            <StatCard
              label="Verified records"
              value={holdings.length}
              hint="Approved and available to you"
              icon={<FileText className="size-4" />}
            />
            <StatCard
              label="Open grievances"
              value={openGrievances}
              tone={openGrievances > 0 ? "attention" : "default"}
              icon={<MessageSquareWarning className="size-4" />}
            />
          </div>
        )}
      </QueryBoundary>

      <Card className="mt-6">
        <CardHeader
          title="My land records"
          description="Each row is a parcel you hold an interest in."
          action={
            <Button asChild variant="ghost" size="sm">
              <Link href="/citizen/map">
                <MapPin aria-hidden />
                View on map
              </Link>
            </Button>
          }
        />

        <QueryBoundary query={parcels} label="your parcels">
          {(data) =>
            data.parcels.length === 0 ? (
              <EmptyState
                title="No parcels are recorded against your name yet"
                description="A parcel appears here once a tehsildar approves a record naming you as a holder."
                action={
                  <Button asChild variant="outline" size="sm">
                    <Link href="/citizen/search">Search public records</Link>
                  </Button>
                }
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Khasra</Th>
                    <Th>Village</Th>
                    <Th>Area</Th>
                    <Th>Share</Th>
                    <Th>Held since</Th>
                    <Th>Class</Th>
                    <Th className="text-right">Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.parcels.map((parcel) => (
                    <tr key={parcel.parcel_id} className="hover:bg-sand-50">
                      <Td>
                        <span className="record-text font-medium text-navy-900">
                          {parcel.khasra_number}
                        </span>
                        <span className="id block text-xs text-sand-500">
                          {parcel.parcel_id}
                        </span>
                      </Td>
                      <Td className="record-text">{parcel.village ?? "—"}</Td>
                      <Td>
                        <span className="id">{parcel.area_value}</span>{" "}
                        <span className="record-text text-sand-700">
                          {parcel.area_unit_raw ?? parcel.area_unit}
                        </span>
                      </Td>
                      <Td className="id">{parcel.share ?? "—"}</Td>
                      <Td className="id text-sand-700">{parcel.held_since ?? "—"}</Td>
                      <Td className="record-text text-sand-700">
                        {parcel.land_class ?? "—"}
                      </Td>
                      <Td className="text-right">
                        <Button asChild variant="link" size="sm">
                          <Link href={`/citizen/records/${parcel.parcel_id}`}>
                            View record
                          </Link>
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )
          }
        </QueryBoundary>
      </Card>
    </>
  );
}
