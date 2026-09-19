"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CircleCheck, CircleX, Send } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { api } from "@/lib/api-client";
import {
  feedbackKeys,
  lrmsKeys,
  type LrmsSyncResult,
  useLrmsStatus,
  useRetrainingPool,
} from "@/lib/queries";
import { Button, Card, CardHeader, EmptyState, Table, Td, Th } from "@mrittika/ui";

const ADAPTER_LABEL: Record<string, string> = {
  file: "File drop for LRMS batch import",
  http: "HTTP push to the state LRMS",
  disabled: "Disabled — queued only",
  misconfigured: "Misconfigured — see the error on each record",
};

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The request failed.";
}

/**
 * §14 — approved records on their way to the state LRMS / DILRMP.
 *
 * Approval queues each record; this card shows the queue and pushes it. A
 * failure is shown with its error and stays queued, never folded into a count
 * of successes.
 */
export function LrmsSyncCard() {
  const status = useLrmsStatus();
  const queryClient = useQueryClient();
  const [result, setResult] = useState<LrmsSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sync = useMutation({
    mutationFn: () => api.post<LrmsSyncResult>("/api/v1/integrations/lrms/sync", {}),
    onSuccess: (summary) => {
      setResult(summary);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: lrmsKeys.status });
    },
    onError: (cause) => setError(errorText(cause)),
  });

  return (
    <Card>
      <CardHeader
        title="LRMS / DILRMP delivery"
        description="Approved Records of Rights, queued on approval and delivered to the state system."
        action={
          <Button size="sm" busy={sync.isPending} onClick={() => sync.mutate()}>
            <Send className="size-3.5" aria-hidden />
            Sync now
          </Button>
        }
      />
      <QueryBoundary query={status} label="the delivery queue">
        {(data) => (
          <div className="p-5">
            <dl className="grid grid-cols-3 gap-3">
              {(
                [
                  ["Delivered", data.counts.DELIVERED],
                  ["Pending", data.counts.PENDING + data.approved_not_queued],
                  ["Failed", data.counts.FAILED],
                ] as const
              ).map(([label, count]) => (
                <div key={label}>
                  <dt className="eyebrow">{label}</dt>
                  <dd className="id mt-1 text-xl font-semibold text-navy-900">{count}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-sand-500">
              Transport: {ADAPTER_LABEL[data.adapter] ?? data.adapter}
            </p>

            {result ? (
              <p className="mt-3 rounded-card bg-sand-50 px-3 py-2 text-sm text-sand-700" role="status">
                Sent {result.attempted}: {result.delivered} delivered, {result.failed} failed
                {result.queued_now ? ` (${result.queued_now} newly queued)` : ""}.
              </p>
            ) : null}
            {error ? (
              <p className="mt-3 rounded-card bg-low-bg px-3 py-2 text-sm text-low" role="alert">
                {error}
              </p>
            ) : null}

            {data.recent.length ? (
              <div className="-mx-5 mt-4 overflow-x-auto border-t border-sand-100">
                <Table>
                  <thead>
                    <tr>
                      <Th>Record</Th>
                      <Th>Status</Th>
                      <Th>Reference or error</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.slice(0, 5).map((row) => (
                      <tr key={`${row.document_id}-${row.payload_sha256}`}>
                        <Td className="id text-navy-900">{row.document_id}</Td>
                        <Td className="text-sm text-sand-700">
                          {row.status.toLowerCase()}
                          {row.attempts > 1 ? ` · ${row.attempts} tries` : ""}
                        </Td>
                        <Td className="max-w-[16rem] truncate text-xs text-sand-500"
                          title={row.last_error ?? row.remote_reference ?? undefined}>
                          {row.last_error ?? row.remote_reference ?? "—"}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            ) : null}
          </div>
        )}
      </QueryBoundary>
    </Card>
  );
}

const REASON_LABEL: Record<string, string> = {
  CONFIDENT_BUT_WRONG: "Confident but wrong",
  MODERATE_MISS: "Moderately confident, wrong",
  UNCERTAIN_AND_WRONG: "Flagged uncertain, wrong",
  MISSED_ENTIRELY: "Missed entirely",
};

/**
 * §67 — the curation step between a verifier's correction and a training run.
 *
 * Most informative first. The values themselves are not shown here by design:
 * the pool is a model-facing view, and record content stays behind the
 * verification screens' own checks.
 */
export function RetrainingPoolCard() {
  const pool = useRetrainingPool();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const review = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "ACCEPTED" | "REJECTED" }) =>
      api.post(`/api/v1/ai/feedback/${id}/review`, { decision }),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: feedbackKeys.pool });
    },
    onError: (cause) => setError(errorText(cause)),
  });

  return (
    <Card>
      <CardHeader
        title="Retraining pool"
        description="Verifier corrections waiting for a decision on whether the model should learn from them."
      />
      <QueryBoundary
        query={pool}
        label="the retraining pool"
        empty={{
          when: (data) => data.pool.length === 0,
          node: (
            <EmptyState
              title="Nothing to review"
              description="Corrections verifiers make will appear here, most informative first."
            />
          ),
        }}
      >
        {(data) => (
          <div>
            <div className="px-5 pt-4">
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-navy-900">Accepted for training</span>
                <span className="id text-sand-700">
                  {data.readiness.accepted} / {data.readiness.threshold}
                </span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-[2px] bg-sand-100" aria-hidden>
                <div
                  className="h-full rounded-[2px] bg-navy-800"
                  style={{
                    width: `${Math.min(1, data.readiness.accepted / data.readiness.threshold) * 100}%`,
                  }}
                />
              </div>
              <p className="mt-1.5 text-xs text-sand-500">
                {data.readiness.ready_to_retrain
                  ? "Enough accepted corrections for a training run: export with scripts/export_feedback_dataset.py."
                  : `${data.readiness.pending_review} awaiting review. Nothing retrains automatically.`}
              </p>
            </div>
            {error ? (
              <p className="mx-5 mt-3 rounded-card bg-low-bg px-3 py-2 text-sm text-low" role="alert">
                {error}
              </p>
            ) : null}
            <ul className="mt-3 divide-y divide-sand-100 border-t border-sand-100">
              {data.pool.map((row) => (
                <li key={row.feedback_id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-navy-900">
                      {row.field?.replaceAll("_", " ").toLowerCase() ?? "field"}
                    </p>
                    <p className="text-xs text-sand-500">
                      {REASON_LABEL[row.selection_reason ?? ""] ?? row.selection_reason}
                      {row.confidence_at_correction !== null
                        ? ` · AI confidence ${row.confidence_at_correction.toFixed(2)}`
                        : ""}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={review.isPending}
                    onClick={() => review.mutate({ id: row.feedback_id, decision: "ACCEPTED" })}
                    aria-label={`Accept the ${row.field ?? ""} correction for training`}
                  >
                    <CircleCheck className="size-3.5" aria-hidden />
                    Accept
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={review.isPending}
                    onClick={() => review.mutate({ id: row.feedback_id, decision: "REJECTED" })}
                    aria-label={`Reject the ${row.field ?? ""} correction`}
                  >
                    <CircleX className="size-3.5" aria-hidden />
                    Reject
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </QueryBoundary>
    </Card>
  );
}
