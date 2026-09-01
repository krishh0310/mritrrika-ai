"use client";

import Link from "next/link";
import { Gavel } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useApprovalQueue } from "@/lib/queries";
import {
  Button, Card, ConfidenceBar, DocumentStatus, EmptyState, Table, Td, Th,
} from "@mrittika/ui";

/** §32 — verified records waiting on a tehsildar's decision. */
export default function ApprovalsQueuePage() {
  const queue = useApprovalQueue();

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Records a verifier has checked. Approving one makes it the record of rights."
      />

      <Card>
        <QueryBoundary
          query={queue}
          label="the approval queue"
          empty={{
            when: (data) => data.documents.length === 0,
            node: (
              <EmptyState
                icon={<Gavel className="size-7" aria-hidden />}
                title="Nothing is waiting for approval"
                description="Records appear here once a verifier submits them."
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
                  <Th>State</Th>
                  <Th>Lowest field confidence</Th>
                  <Th>Flags</Th>
                  <Th className="text-right">Action</Th>
                </tr>
              </thead>
              <tbody>
                {data.documents.map((task) => (
                  <tr key={task.document_id} className="hover:bg-sand-50">
                    <Td className="id text-navy-900">{task.document_id}</Td>
                    <Td className="text-sand-700">
                      {task.document_type?.replaceAll("_", " ") ?? "—"}
                    </Td>
                    <Td>
                      <DocumentStatus state={task.state} />
                    </Td>
                    <Td>
                      <ConfidenceBar score={task.lowest_confidence} />
                    </Td>
                    <Td className="id text-sand-700">{task.anomaly_count || "—"}</Td>
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
    </>
  );
}
