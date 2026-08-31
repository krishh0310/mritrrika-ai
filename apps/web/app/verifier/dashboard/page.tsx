"use client";

import Link from "next/link";
import {
  AlertTriangle, CheckCircle2, CircleAlert, Eye, TriangleAlert, UserCheck,
} from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useVerificationQueue, useVerifierDashboard } from "@/lib/queries";
import {
  Button, Card, CardHeader, ConfidenceBar, EmptyState, StatCard, Table, Td, Th,
} from "@mrittika/ui";

/** §27 cards. "Assigned" is this verifier's; the rest describe the shared queue. */
const CARDS = [
  { key: "assigned", label: "Assigned to you", icon: UserCheck },
  { key: "needs_review", label: "Waiting in queue", icon: Eye },
  { key: "low_confidence", label: "Low confidence", icon: CircleAlert, alert: true },
  { key: "medium_confidence", label: "Medium confidence", icon: TriangleAlert },
  { key: "anomaly_flagged", label: "Flagged", icon: AlertTriangle, alert: true },
  { key: "completed_today", label: "Completed today", icon: CheckCircle2 },
] as const;

export default function VerifierDashboardPage() {
  const dashboard = useVerifierDashboard();
  const queue = useVerificationQueue();

  const next = (queue.data?.tasks ?? []).slice(0, 5);

  return (
    <>
      <PageHeader
        title="Verification"
        description="Check what the models read, correct what they got wrong, and pass the record on."
        actions={
          <Button asChild>
            <Link href="/verifier/queue">Open the queue</Link>
          </Button>
        }
      />

      <QueryBoundary query={dashboard} label="your dashboard">
        {(data) => (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {CARDS.map(({ key, label, icon: Icon, ...rest }) => {
              const value = data.cards[key] ?? 0;
              const alert = "alert" in rest && rest.alert;
              return (
                <StatCard
                  key={key}
                  label={label}
                  value={value}
                  icon={<Icon className="size-4" />}
                  tone={alert && value > 0 ? "attention" : "default"}
                />
              );
            })}
          </div>
        )}
      </QueryBoundary>

      <Card className="mt-6">
        <CardHeader
          title="Next up"
          description="The five documents that most need a human look."
          action={
            <Button asChild variant="ghost" size="sm">
              <Link href="/verifier/queue">See all</Link>
            </Button>
          }
        />
        <QueryBoundary
          query={queue}
          label="the queue"
          empty={{
            when: (data) => data.tasks.length === 0,
            node: (
              <EmptyState
                title="The queue is clear"
                description="Nothing is waiting for verification right now."
              />
            ),
          }}
        >
          {() => (
            <Table>
              <thead>
                <tr>
                  <Th>Document</Th>
                  <Th>Type</Th>
                  <Th>Lowest confidence</Th>
                  <Th>Flags</Th>
                  <Th className="text-right">Action</Th>
                </tr>
              </thead>
              <tbody>
                {next.map((task) => (
                  <tr key={task.task_id} className="hover:bg-sand-50">
                    <Td className="id text-navy-900">{task.document_id}</Td>
                    <Td className="text-sand-700">
                      {task.document_type.replaceAll("_", " ")}
                    </Td>
                    <Td>
                      <ConfidenceBar score={task.lowest_confidence} />
                    </Td>
                    <Td className="id text-sand-700">
                      {task.anomaly_count || "—"}
                    </Td>
                    <Td className="text-right">
                      <Button asChild size="sm">
                        <Link href={`/verifier/documents/${task.document_id}`}>
                          Verify
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
    </>
  );
}
