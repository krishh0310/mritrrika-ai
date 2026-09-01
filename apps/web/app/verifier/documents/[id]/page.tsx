"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { AlertTriangle, ArrowLeft, Send } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { DocumentViewer } from "@/components/verifier/document-viewer";
import { FieldEditor } from "@/components/verifier/field-editor";
import { ApiError, api } from "@/lib/api-client";
import { useVerificationWorkspace } from "@/lib/queries";
import {
  Button, Card, ConfidenceBadge, DocumentStatus, SyntheticNotice, bandFor,
} from "@mrittika/ui";

/**
 * The verification workspace (§28) — the most important screen in the system.
 *
 * Split screen: the scan on the left, its extracted fields on the right, one
 * shared selection between them. Clicking a field zooms the document to the
 * region it was read from; clicking a box on the document focuses the field.
 *
 * Fields are ordered lowest-confidence first. A verifier's time is the scarce
 * resource, and the whole point of scoring each field separately (§8) is to
 * spend that time where the model is least sure.
 */
export default function VerificationWorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const workspace = useVerificationWorkspace(id);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A presigned URL, fetched separately so a missing scan does not take the
  // whole workspace down with it (§85).
  const scan = useQuery({
    queryKey: ["document", id, "file"],
    retry: false,
    queryFn: () => api.get<{ url: string }>(`/api/v1/documents/${id}/file`),
  });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["verifications", id] });
    void queryClient.invalidateQueries({ queryKey: ["verifications"] });
  }

  const correct = useMutation({
    mutationFn: ({ extractionId, value }: { extractionId: string; value: string }) =>
      api.patch(`/api/v1/verifications/extractions/${extractionId}`, { value }),
    onSuccess: refresh,
    onError: (cause) =>
      setError(cause instanceof ApiError ? cause.message : "The correction failed."),
  });

  const accept = useMutation({
    mutationFn: (extractionId: string) =>
      api.post(`/api/v1/verifications/extractions/${extractionId}/approve`, {}),
    onSuccess: refresh,
    onError: (cause) =>
      setError(cause instanceof ApiError ? cause.message : "Could not accept that field."),
  });

  const submit = useMutation({
    mutationFn: () => api.post(`/api/v1/verifications/${id}/submit`, {}),
    onSuccess: refresh,
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The verification could not be submitted.",
      ),
  });

  return (
    <QueryBoundary query={workspace} label="the workspace">
      {(data) => {
        // Lowest confidence first; already-handled fields sink to the bottom.
        const ordered = [...data.fields].sort((a, b) => {
          // Statuses are packages/domain's FieldStatus (see field-editor.tsx).
          const handled = (f: typeof a) =>
            f.corrected_value ||
            f.status === "VERIFIER_APPROVED" ||
            f.status === "AUTO_ACCEPTED"
              ? 1
              : 0;
          if (handled(a) !== handled(b)) return handled(a) - handled(b);
          return (a.final_confidence ?? 1) - (b.final_confidence ?? 1);
        });

        const needsReview = data.fields.filter(
          (f) => bandFor(f.final_confidence) !== "HIGH" && !f.corrected_value,
        ).length;
        const submitted = data.state === "VERIFIED" || data.state === "PENDING_APPROVAL";

        return (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <Button asChild variant="link" size="sm" className="-ml-3">
                <Link href="/verifier/queue">
                  <ArrowLeft aria-hidden />
                  Queue
                </Link>
              </Button>
              <h1 className="id text-lg font-semibold text-navy-900">
                {data.document_id}
              </h1>
              <span className="text-sm text-sand-500">
                {data.document_type.replaceAll("_", " ")}
              </span>
              <DocumentStatus state={data.state} />
              <SyntheticNotice />

              <div className="ml-auto flex items-center gap-3">
                <span className="text-sm text-sand-700">
                  <span className="id font-semibold text-navy-900">{needsReview}</span>{" "}
                  {needsReview === 1 ? "field needs" : "fields need"} a look
                </span>
                <Button
                  busy={submit.isPending}
                  disabled={submitted}
                  onClick={() => submit.mutate()}
                >
                  <Send aria-hidden />
                  {submitted ? "Submitted" : "Submit verification"}
                </Button>
              </div>
            </div>

            {error ? (
              <p
                role="alert"
                className="mb-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low"
              >
                {error}
              </p>
            ) : null}

            {submit.isSuccess ? (
              <p
                role="status"
                className="mb-4 rounded-card border border-high/30 bg-high-bg px-3 py-2 text-sm text-high"
              >
                Verification submitted. This document is now with the tehsildar.
              </p>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-2">
              <DocumentViewer
                className="h-[36rem] lg:h-[calc(100dvh-14rem)]"
                imageUrl={scan.data?.url ?? null}
                pageWidth={data.page.width}
                pageHeight={data.page.height}
                fields={data.fields}
                ocrBlocks={data.ocr_blocks}
                selectedField={selected}
                onSelectField={setSelected}
              />

              <Card className="flex h-[36rem] flex-col overflow-hidden lg:h-[calc(100dvh-14rem)]">
                <div className="flex items-center justify-between gap-3 border-b border-sand-200 px-4 py-3">
                  <div>
                    <h2 className="text-sm font-semibold text-navy-900">
                      Extracted fields
                    </h2>
                    <p className="mt-0.5 text-xs text-sand-500">
                      Least certain first. Corrections are stored beside the
                      prediction, never over it.
                    </p>
                  </div>
                  <ConfidenceLegend />
                </div>

                {data.findings.filter((f) => !f.field).length > 0 ? (
                  <div className="border-b border-sand-200 bg-medium-bg px-4 py-3">
                    {data.findings
                      .filter((f) => !f.field)
                      .map((finding) => (
                        <p
                          key={finding.rule}
                          className="flex items-start gap-1.5 text-xs text-medium"
                        >
                          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
                          {finding.message}
                        </p>
                      ))}
                  </div>
                ) : null}

                <div className="divide-y divide-sand-100 overflow-y-auto">
                  {ordered.map((field) => (
                    <FieldEditor
                      key={field.extraction_id}
                      field={field}
                      findings={data.findings}
                      selected={selected === field.extraction_id}
                      onSelect={() => setSelected(field.extraction_id)}
                      readOnly={submitted}
                      busy={
                        (correct.isPending &&
                          correct.variables?.extractionId === field.extraction_id) ||
                        (accept.isPending && accept.variables === field.extraction_id)
                      }
                      onCorrect={(value) => {
                        setError(null);
                        correct.mutate({ extractionId: field.extraction_id, value });
                      }}
                      onAccept={() => {
                        setError(null);
                        accept.mutate(field.extraction_id);
                      }}
                    />
                  ))}
                </div>
              </Card>
            </div>
          </>
        );
      }}
    </QueryBoundary>
  );
}

/** What the box colours on the document mean. */
function ConfidenceLegend() {
  return (
    <div className="hidden items-center gap-1.5 sm:flex">
      {([0.95, 0.7, 0.4] as const).map((score) => (
        <ConfidenceBadge key={score} score={score} showScore={false} />
      ))}
    </div>
  );
}
