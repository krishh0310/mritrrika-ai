"use client";

import Link from "next/link";
import {
  AlertTriangle, CheckCircle2, Clock, Gauge, Hourglass, ListChecks, TrendingUp, Undo2,
} from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useAnomalies, useApprovalQueue, useTehsildarDashboard } from "@/lib/queries";
import {
  Button, Card, CardHeader, ConfidenceBar, EmptyState, StatCard, Table, Td, Th,
} from "@mrittika/ui";

/** Format seconds the way an officer reads them, not as a raw float. */
function duration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export default function TehsildarDashboardPage() {
  const dashboard = useTehsildarDashboard();
  const queue = useApprovalQueue();
  const anomalies = useAnomalies("OPEN");

  return (
    <>
      <PageHeader
        title="Administration"
        description="What is waiting for your decision, and how digitization is progressing across the tehsil."
        actions={
          <Button asChild>
            <Link href="/tehsildar/approvals">Open approvals</Link>
          </Button>
        }
      />

      <QueryBoundary query={dashboard} label="your dashboard">
        {(data) => (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Pending approval"
                value={data.cards.pending_approval ?? 0}
                icon={<Hourglass className="size-4" />}
                tone={(data.cards.pending_approval ?? 0) > 0 ? "attention" : "default"}
              />
              <StatCard
                label="Approved today"
                value={data.cards.approved_today ?? 0}
                icon={<CheckCircle2 className="size-4" />}
                tone="good"
              />
              <StatCard
                label="Returned"
                value={data.cards.returned ?? 0}
                hint="Sent back to a verifier"
                icon={<Undo2 className="size-4" />}
              />
              <StatCard
                label="Potential inconsistencies"
                value={data.cards.potential_inconsistencies ?? 0}
                hint="Flagged for investigation, not proven"
                icon={<AlertTriangle className="size-4" />}
                tone={
                  (data.cards.potential_inconsistencies ?? 0) > 0
                    ? "attention"
                    : "default"
                }
              />
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Extraction accuracy"
                value={
                  data.cards.extraction_accuracy === null ||
                  data.cards.extraction_accuracy === undefined
                    ? "—"
                    : `${(data.cards.extraction_accuracy * 100).toFixed(1)}%`
                }
                hint={`Fields kept unchanged by verifiers, of ${data.totals.accuracy_fields_reviewed ?? 0} reviewed`}
                icon={<ListChecks className="size-4" />}
              />
              <StatCard
                label="Average AI confidence"
                value={data.cards.average_ai_confidence?.toFixed(2) ?? "—"}
                hint="Across every extracted field on file"
                icon={<Gauge className="size-4" />}
              />
              <StatCard
                label="Average verification time"
                value={duration(data.cards.average_verification_seconds)}
                hint="Pick-up to submission"
                icon={<Clock className="size-4" />}
              />
              <StatCard
                label="Digitization progress"
                value={`${Math.round((data.cards.digitization_progress ?? 0) * 100)}%`}
                hint={`${data.totals.approved} of ${data.totals.documents} documents approved`}
                icon={<TrendingUp className="size-4" />}
              />
            </div>
          </>
        )}
      </QueryBoundary>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Awaiting your approval"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href="/tehsildar/approvals">See all</Link>
              </Button>
            }
          />
          <QueryBoundary
            query={queue}
            label="the approval queue"
            empty={{
              when: (data) => data.documents.length === 0,
              node: (
                <EmptyState
                  title="Nothing is waiting"
                  description="Verified records will appear here for your decision."
                />
              ),
            }}
          >
            {(data) => (
              <Table>
                <thead>
                  <tr>
                    <Th>Document</Th>
                    <Th>Type</Th>
                    <Th>Lowest confidence</Th>
                    <Th className="text-right">Review</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.documents.slice(0, 6).map((task) => (
                    <tr key={task.document_id} className="hover:bg-sand-50">
                      <Td className="id text-navy-900">{task.document_id}</Td>
                      <Td className="text-sand-700">
                        {task.document_type?.replaceAll("_", " ") ?? "—"}
                      </Td>
                      <Td>
                        <ConfidenceBar score={task.lowest_confidence} />
                      </Td>
                      <Td className="text-right">
                        <Button asChild size="sm">
                          <Link href={`/tehsildar/approvals/${task.document_id}`}>
                            Review
                          </Link>
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </QueryBoundary>
        </Card>

        <Card>
          <CardHeader
            title="Potential inconsistencies"
            description="Patterns worth a human look. None of these is a finding of wrongdoing."
          />
          <QueryBoundary
            query={anomalies}
            label="the flags"
            empty={{
              when: (data) => data.flags.length === 0,
              node: (
                <EmptyState
                  title="Nothing flagged"
                  description="No record currently shows a pattern the checks would question."
                />
              ),
            }}
          >
            {(data) => (
              <ul className="divide-y divide-sand-100">
                {data.flags.slice(0, 5).map((flag) => (
                  <li key={flag.flag_id} className="px-5 py-3.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="text-sm font-medium text-navy-900">
                        {flag.anomaly_type.replaceAll("_", " ").toLowerCase()}
                      </span>
                      <span className="id text-xs text-sand-500">
                        {flag.khasra_number ? `khasra ${flag.khasra_number}` : flag.parcel_id}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-sand-700">{flag.explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </QueryBoundary>
        </Card>
      </div>
    </>
  );
}
