"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, Inbox } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useVerificationQueue } from "@/lib/queries";
import {
  Button, Card, ConfidenceBar, DocumentStatus, EmptyState, Select, Table, Td,
  Th, bandFor,
} from "@mrittika/ui";

/**
 * §27 — the work queue.
 *
 * Ordered by the API (priority, then lowest confidence). The filters here
 * narrow that ordering rather than replacing it, so the hardest document stays
 * at the top of whatever subset the verifier chooses to look at.
 */
export default function VerifierQueuePage() {
  const queue = useVerificationQueue();
  const [type, setType] = useState("");
  const [band, setBand] = useState("");
  const [flagged, setFlagged] = useState("");

  const tasks = queue.data?.tasks ?? [];

  const documentTypes = useMemo(
    () => [...new Set(tasks.map((t) => t.document_type))].sort(),
    [tasks],
  );

  const filtered = tasks.filter((task) => {
    if (type && task.document_type !== type) return false;
    if (band && bandFor(task.lowest_confidence) !== band) return false;
    if (flagged === "yes" && task.anomaly_count === 0) return false;
    if (flagged === "no" && task.anomaly_count > 0) return false;
    return true;
  });

  return (
    <>
      <PageHeader
        title="Verification queue"
        description="Hardest first: lowest confidence and flagged records come to the top."
        actions={
          <div className="flex flex-wrap gap-2">
            <Select
              value={type}
              onChange={(e) => setType(e.target.value)}
              aria-label="Document type"
              className="w-44"
            >
              <option value="">All types</option>
              {documentTypes.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
            <Select
              value={band}
              onChange={(e) => setBand(e.target.value)}
              aria-label="Confidence"
              className="w-44"
            >
              <option value="">Any confidence</option>
              <option value="LOW">Low only</option>
              <option value="MEDIUM">Medium only</option>
              <option value="HIGH">High only</option>
            </Select>
            <Select
              value={flagged}
              onChange={(e) => setFlagged(e.target.value)}
              aria-label="Flagged"
              className="w-44"
            >
              <option value="">Flagged or not</option>
              <option value="yes">Flagged only</option>
              <option value="no">Unflagged only</option>
            </Select>
          </div>
        }
      />

      <Card>
        <QueryBoundary
          query={queue}
          label="the queue"
          empty={{
            when: (data) => data.tasks.length === 0,
            node: (
              <EmptyState
                icon={<Inbox className="size-7" aria-hidden />}
                title="Nothing is waiting for verification"
                description="Documents appear here once an operator has put them through the pipeline."
              />
            ),
          }}
        >
          {() =>
            filtered.length === 0 ? (
              <EmptyState
                title="No documents match those filters"
                description="Widen the filters to see the rest of the queue."
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setType("");
                      setBand("");
                      setFlagged("");
                    }}
                  >
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Priority</Th>
                    <Th>Document</Th>
                    <Th>Type</Th>
                    <Th>State</Th>
                    <Th>Lowest field confidence</Th>
                    <Th>Scan quality</Th>
                    <Th>Flags</Th>
                    <Th className="text-right">Action</Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((task) => (
                    <tr key={task.task_id} className="hover:bg-sand-50">
                      <Td>
                        <span
                          className="id inline-flex size-6 items-center justify-center rounded-chip bg-navy-100 text-xs font-semibold text-navy-800"
                          title={`Priority ${task.priority} — 1 is highest`}
                        >
                          {task.priority}
                        </span>
                      </Td>
                      <Td className="id text-navy-900">{task.document_id}</Td>
                      <Td className="text-sand-700">
                        {task.document_type.replaceAll("_", " ")}
                      </Td>
                      <Td>
                        <DocumentStatus state={task.state} />
                      </Td>
                      <Td>
                        <ConfidenceBar score={task.lowest_confidence} />
                      </Td>
                      <Td>
                        <ConfidenceBar score={task.quality_score} />
                      </Td>
                      <Td>
                        {task.anomaly_count > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-chip bg-medium-bg px-1.5 py-0.5 text-xs font-medium text-medium">
                            <AlertTriangle className="size-3" aria-hidden />
                            {task.anomaly_count}
                          </span>
                        ) : (
                          <span className="text-xs text-sand-300">none</span>
                        )}
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
            )
          }
        </QueryBoundary>
      </Card>
    </>
  );
}
