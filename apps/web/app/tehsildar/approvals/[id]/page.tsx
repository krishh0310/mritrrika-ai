"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import {
  AlertTriangle, ArrowLeft, Check, ScanLine, Undo2, X,
} from "lucide-react";

import { OwnershipTimeline } from "@/components/shared/ownership-timeline";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { ApiError, api } from "@/lib/api-client";
import { fieldLabel } from "@/lib/field-labels";
import { useApprovalWorkspace } from "@/lib/queries";
import {
  Button, Card, CardHeader, ConfidenceBadge, DocumentStatus, ProvenanceStrip, RecordText,
  RoleBadge, SyntheticNotice, Table, Td, Textarea, Th,
} from "@mrittika/ui";

/**
 * §32 — the approval workspace.
 *
 * The verifier asked "is this page transcribed correctly?". This screen asks
 * "should this become the record of rights?", which needs different evidence:
 * what the verifier changed, the parcel's ownership and mutation history, any
 * flagged inconsistency, and the audit trail of how it got here.
 *
 * Every decision except approval demands a reason. A record returned or
 * rejected without one leaves the next person guessing.
 */
export default function ApprovalWorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const workspace = useApprovalWorkspace(id);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: ({ action, why }: { action: string; why?: string }) =>
      api.post(`/api/v1/approvals/${id}/${action}`, why ? { reason: why } : {}),
    onSuccess: (_result, variables) => {
      setError(null);
      setReason("");
      setDone(variables.action);
      void queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The decision could not be recorded.",
      ),
  });

  return (
    <QueryBoundary query={workspace} label="the record">
      {(data) => {
        const decided = data.state === "APPROVED" || data.state === "REJECTED";
        const needsReason = reason.trim().length === 0;

        return (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <Button asChild variant="link" size="sm" className="-ml-3">
                <Link href="/tehsildar/approvals">
                  <ArrowLeft aria-hidden />
                  Approvals
                </Link>
              </Button>
              <h1 className="id text-lg font-semibold text-navy-900">
                {data.document_id}
              </h1>
              <DocumentStatus state={data.state} />
              <SyntheticNotice />
            </div>

            {error ? (
              <p role="alert" className="mb-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low">
                {error}
              </p>
            ) : null}

            {done ? (
              <p role="status" className="mb-4 rounded-card border border-high/30 bg-high-bg px-3 py-2 text-sm text-high">
                Decision recorded: {done}. It is now in the audit trail.
              </p>
            ) : null}

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
              <div className="space-y-5">
                <Card>
                  <CardHeader
                    title="The record"
                    description="What would become the record of rights if you approve."
                  />
                  <Table>
                    <thead>
                      <tr>
                        <Th>Field</Th>
                        <Th>Value and provenance</Th>
                        <Th>Confidence</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.fields.map((field) => (
                        <tr key={field.extraction_id}>
                          <Td className="whitespace-nowrap text-sand-700">
                            {fieldLabel(field.field)}
                          </Td>
                          <Td>
                            <ProvenanceStrip
                              raw={field.raw_value}
                              normalized={field.normalized_value}
                              corrected={field.corrected_value}
                            />
                          </Td>
                          <Td>
                            <ConfidenceBadge score={field.final_confidence} />
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </Card>

                {data.anomalies.length > 0 ? (
                  <Card>
                    <CardHeader
                      title="Potential inconsistencies"
                      description="Patterns the checks would question. Not a finding of wrongdoing."
                    />
                    <ul className="divide-y divide-sand-100">
                      {data.anomalies.map((flag) => (
                        <li key={flag.anomaly_type} className="px-5 py-4">
                          <p className="flex items-center gap-2 text-sm font-medium text-navy-900">
                            <AlertTriangle className="size-4 text-medium" aria-hidden />
                            {flag.anomaly_type.replaceAll("_", " ").toLowerCase()}
                          </p>
                          <p className="mt-1 text-sm text-sand-700">{flag.explanation}</p>
                          {flag.evidence ? (
                            <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                              {Object.entries(flag.evidence).map(([key, value]) => (
                                <div key={key} className="flex items-baseline gap-1.5">
                                  <dt className="eyebrow">{key.replaceAll("_", " ")}</dt>
                                  <dd className="id text-xs text-sand-700">
                                    {typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </Card>
                ) : null}

                <Card>
                  <CardHeader
                    title="Verifier corrections"
                    description="What a human changed, and away from what."
                  />
                  {data.corrections.length === 0 ? (
                    <p className="px-5 py-4 text-sm text-sand-500">
                      The verifier accepted the extraction without changing anything.
                    </p>
                  ) : (
                    <Table>
                      <thead>
                        <tr>
                          <Th>Field</Th>
                          <Th>Model said</Th>
                          <Th>Corrected to</Th>
                          <Th>Confidence then</Th>
                          <Th>By</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.corrections.map((correction, index) => (
                          <tr key={`${correction.field}-${index}`}>
                            <Td className="text-sand-700">{fieldLabel(correction.field)}</Td>
                            <Td className="text-sand-500 line-through">
                              <RecordText value={correction.model_prediction} stacked />
                            </Td>
                            <Td className="font-medium text-navy-900">
                              <RecordText value={correction.corrected_value} stacked />
                            </Td>
                            <Td>
                              <ConfidenceBadge
                                score={correction.confidence_at_correction}
                                showScore={false}
                              />
                            </Td>
                            <Td className="text-xs text-sand-500">
                              {correction.corrected_by ?? "—"}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Card>
              </div>

              <div className="space-y-5">
                <Card>
                  <CardHeader title="Your decision" />
                  <div className="space-y-3 p-5">
                    <Textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Why are you returning or rejecting this? The verifier and the audit trail will both see it."
                      aria-label="Reason"
                      disabled={decided}
                    />

                    <Button
                      className="w-full"
                      busy={decide.isPending && decide.variables?.action === "approve"}
                      disabled={decided}
                      onClick={() =>
                        decide.mutate({ action: "approve", why: reason.trim() || undefined })
                      }
                    >
                      <Check aria-hidden />
                      Approve this record
                    </Button>

                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        variant="outline"
                        busy={decide.isPending && decide.variables?.action === "return"}
                        disabled={decided || needsReason}
                        onClick={() => decide.mutate({ action: "return", why: reason.trim() })}
                      >
                        <Undo2 aria-hidden />
                        Return
                      </Button>
                      <Button
                        variant="danger"
                        busy={decide.isPending && decide.variables?.action === "reject"}
                        disabled={decided || needsReason}
                        onClick={() => decide.mutate({ action: "reject", why: reason.trim() })}
                      >
                        <X aria-hidden />
                        Reject
                      </Button>
                    </div>

                    {needsReason && !decided ? (
                      <p className="flex items-start gap-1.5 text-xs text-sand-500">
                        <ScanLine className="mt-px size-3.5 shrink-0" aria-hidden />
                        Returning or rejecting needs a reason. Approving does not.
                      </p>
                    ) : null}
                  </div>
                </Card>

                {data.parcel ? (
                  <Card>
                    <CardHeader
                      title={`Parcel ${data.parcel.khasra_number}`}
                      description={<span className="id text-xs">{data.parcel.parcel_id}</span>}
                    />
                    <div className="p-5">
                      <OwnershipTimeline history={data.ownership_history} />
                    </div>
                  </Card>
                ) : (
                  <Card>
                    <CardHeader title="No linked parcel" />
                    <p className="px-5 py-4 text-sm text-sand-700">
                      {data.unlinked_reason ??
                        "This document is not linked to a parcel, so no history is available."}
                    </p>
                  </Card>
                )}

                <Card>
                  <CardHeader
                    title="Audit trail"
                    description="Every step this document has been through."
                    action={
                      <Button asChild variant="ghost" size="sm">
                        <Link href={`/audit/${data.document_id}`}>Full trail</Link>
                      </Button>
                    }
                  />
                  <ol className="divide-y divide-sand-100">
                    {data.audit_timeline.map((event) => (
                      <li
                        key={event.sequence}
                        className="flex items-baseline gap-3 px-5 py-2.5 text-sm"
                      >
                        <span className="id w-8 shrink-0 text-xs text-sand-300">
                          {event.sequence}
                        </span>
                        <span className="flex-1 text-sand-700">
                          {event.action.replaceAll(".", " · ")}
                        </span>
                        {event.actor_role ? <RoleBadge role={event.actor_role} /> : null}
                      </li>
                    ))}
                  </ol>
                </Card>
              </div>
            </div>
          </>
        );
      }}
    </QueryBoundary>
  );
}
