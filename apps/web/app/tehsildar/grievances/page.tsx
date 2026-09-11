"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { MessageSquareWarning } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { ApiError, api } from "@/lib/api-client";
import { useGrievanceQueue } from "@/lib/queries";
import {
  Button, Card, EmptyState, GrievanceStatus, Select, Table, Td, Textarea, Th, RecordText,
} from "@mrittika/ui";

/**
 * §19 / §31 — the grievance review queue.
 *
 * The status control offers only the transitions the API will actually allow
 * from the row's current status. Offering "Resolve" on a SUBMITTED grievance
 * would just produce a 409 the officer cannot act on.
 */
const NEXT_STATUSES: Record<string, string[]> = {
  SUBMITTED: ["UNDER_REVIEW", "REJECTED"],
  UNDER_REVIEW: ["ACTION_REQUIRED", "RESOLVED", "REJECTED"],
  ACTION_REQUIRED: ["UNDER_REVIEW", "RESOLVED", "REJECTED"],
  RESOLVED: [],
  REJECTED: [],
};

const STATUS_VERBS: Record<string, string> = {
  UNDER_REVIEW: "Start review",
  ACTION_REQUIRED: "Needs action",
  RESOLVED: "Resolve",
  REJECTED: "Reject",
};

export default function TehsildarGrievancesPage() {
  const [filter, setFilter] = useState<string>("");
  const queue = useGrievanceQueue(filter || undefined);
  const queryClient = useQueryClient();

  const [openId, setOpenId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const advance = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.post(`/api/v1/grievances/${id}/status`, {
        status,
        note: note.trim() || undefined,
      }),
    onSuccess: () => {
      setNote("");
      setOpenId(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["grievances"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError ? cause.message : "Could not update that grievance.",
      ),
  });

  return (
    <>
      <PageHeader
        title="Grievances"
        description="Issues citizens have raised about their records."
        actions={
          <Select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-48"
            aria-label="Status"
          >
            <option value="">All statuses</option>
            {["SUBMITTED", "UNDER_REVIEW", "ACTION_REQUIRED", "RESOLVED", "REJECTED"].map(
              (status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ").toLowerCase()}
                </option>
              ),
            )}
          </Select>
        }
      />

      {error ? (
        <p role="alert" className="mb-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low">
          {error}
        </p>
      ) : null}

      <Card>
        <QueryBoundary
          query={queue}
          label="the grievance queue"
          empty={{
            when: (data) => data.grievances.length === 0,
            node: (
              <EmptyState
                icon={<MessageSquareWarning className="size-7" aria-hidden />}
                title="No grievances to review"
                description="Nothing has been raised under this filter."
              />
            ),
          }}
        >
          {(data) => (
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Raised by</Th>
                  <Th>Issue</Th>
                  <Th>Parcel</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Decide</Th>
                </tr>
              </thead>
              <tbody>
                {data.grievances.map((grievance) => {
                  const next = NEXT_STATUSES[grievance.status] ?? [];
                  const open = openId === grievance.grievance_id;
                  return (
                    <tr key={grievance.grievance_id} className="align-top">
                      <Td className="id text-sand-700">{grievance.grievance_id}</Td>
                      <Td>
                        <RecordText value={grievance.raised_by} stacked />
                      </Td>
                      <Td>
                        <p className="text-navy-900">
                          {grievance.issue_type.replaceAll("_", " ").toLowerCase()}
                        </p>
                        <p className="mt-0.5 max-w-md text-xs text-sand-500">
                          {grievance.description}
                        </p>
                        {open ? (
                          <Textarea
                            className="mt-2"
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="What did you find? The citizen will see this."
                            aria-label="Note to the citizen"
                          />
                        ) : grievance.resolution_note ? (
                          <p className="mt-1.5 rounded-chip bg-sand-50 px-2 py-1 text-xs text-sand-700">
                            {grievance.resolution_note}
                          </p>
                        ) : null}
                      </Td>
                      <Td className="record-text">{grievance.khasra_number ?? "—"}</Td>
                      <Td>
                        <GrievanceStatus status={grievance.status} />
                      </Td>
                      <Td className="text-right">
                        {next.length === 0 ? (
                          <span className="text-xs text-sand-300">closed</span>
                        ) : open ? (
                          <div className="flex flex-col items-end gap-1.5">
                            {next.map((status) => (
                              <Button
                                key={status}
                                size="sm"
                                variant={status === "REJECTED" ? "danger" : "outline"}
                                busy={
                                  advance.isPending &&
                                  advance.variables?.id === grievance.grievance_id &&
                                  advance.variables?.status === status
                                }
                                onClick={() =>
                                  advance.mutate({
                                    id: grievance.grievance_id,
                                    status,
                                  })
                                }
                              >
                                {STATUS_VERBS[status] ?? status}
                              </Button>
                            ))}
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => {
                                setOpenId(null);
                                setNote("");
                              }}
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setOpenId(grievance.grievance_id);
                              setNote("");
                              setError(null);
                            }}
                          >
                            Act on this
                          </Button>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </QueryBoundary>
      </Card>
    </>
  );
}
