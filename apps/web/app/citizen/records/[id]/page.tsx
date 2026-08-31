"use client";

import Link from "next/link";
import { use } from "react";
import { ArrowLeft, MapPin, MessageSquareWarning, Sparkles } from "lucide-react";

import { OwnershipTimeline } from "@/components/shared/ownership-timeline";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useMyParcels, useOwnershipHistory } from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, ForbiddenState, SyntheticNotice,
} from "@mrittika/ui";

/**
 * One parcel, as its holder sees it.
 *
 * Deliberately thin on machine detail: §17 forbids showing a citizen raw OCR,
 * internal confidence, verification notes or anomaly scores. What they get is
 * the approved record and its history — which is what a record of rights
 * actually is.
 */
export default function CitizenRecordPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const parcels = useMyParcels();
  const history = useOwnershipHistory(id);

  const parcel = parcels.data?.parcels.find((p) => p.parcel_id === id);

  return (
    <>
      <Button asChild variant="link" size="sm" className="mb-2 -ml-3">
        <Link href="/citizen/my-land">
          <ArrowLeft aria-hidden />
          Back to my land
        </Link>
      </Button>

      <QueryBoundary query={parcels} label="your parcels">
        {() =>
          !parcel ? (
            // The API returns 403 for both "not yours" and "does not exist", so
            // the UI must not claim the parcel is missing (§62).
            <Card>
              <ForbiddenState description="This parcel is not recorded against your name. If you believe it should be, raise a grievance." />
            </Card>
          ) : (
            <>
              <PageHeader
                title={`Khasra ${parcel.khasra_number}`}
                description={
                  <span className="id text-sand-500">{parcel.parcel_id}</span>
                }
                actions={
                  <>
                    <Button asChild variant="outline">
                      <Link href={`/citizen/map?parcel=${parcel.parcel_id}`}>
                        <MapPin aria-hidden />
                        View parcel
                      </Link>
                    </Button>
                    <Button asChild variant="outline">
                      <Link
                        href={`/citizen/assistant?q=${encodeURIComponent(
                          `Explain the ownership history of khasra ${parcel.khasra_number}.`,
                        )}`}
                      >
                        <Sparkles aria-hidden />
                        Ask AI
                      </Link>
                    </Button>
                    <Button asChild variant="ghost">
                      <Link href={`/citizen/grievances?parcel=${parcel.parcel_id}`}>
                        <MessageSquareWarning aria-hidden />
                        Raise a grievance
                      </Link>
                    </Button>
                  </>
                }
              />

              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                <Card>
                  <CardHeader
                    title="Record of rights"
                    action={<SyntheticNotice />}
                  />
                  <dl className="grid grid-cols-2 gap-x-5 gap-y-4 p-5">
                    {[
                      ["Khasra number", parcel.khasra_number, "record-text"],
                      ["Khata number", parcel.khata_number ?? "—", "id"],
                      ["Village", parcel.village ?? "—", "record-text"],
                      ["Land classification", parcel.land_class ?? "—", "record-text"],
                      [
                        "Recorded area",
                        `${parcel.area_value} ${parcel.area_unit_raw ?? parcel.area_unit}`,
                        "record-text",
                      ],
                      ["Your share", parcel.share ?? "—", "id"],
                      ["Held since", parcel.held_since ?? "—", "id"],
                    ].map(([label, value, face]) => (
                      <div key={label}>
                        <dt className="eyebrow">{label}</dt>
                        <dd className={`mt-1 text-[0.9375rem] text-navy-900 ${face}`}>
                          {value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </Card>

                <Card>
                  <CardHeader
                    title="Ownership and mutation history"
                    description="Every recorded change to who holds this parcel."
                  />
                  <div className="p-5">
                    <QueryBoundary query={history} label="the ownership history">
                      {(data) =>
                        data.history.length === 0 ? (
                          <EmptyState
                            title="No history recorded"
                            description="Only the current holding is on file for this parcel."
                          />
                        ) : (
                          <OwnershipTimeline history={data.history} />
                        )
                      }
                    </QueryBoundary>
                  </div>
                </Card>
              </div>
            </>
          )
        }
      </QueryBoundary>
    </>
  );
}
