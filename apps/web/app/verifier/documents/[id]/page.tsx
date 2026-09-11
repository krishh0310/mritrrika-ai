"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, RotateCw, Send } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { DocumentViewer } from "@/components/verifier/document-viewer";
import { FieldEditor } from "@/components/verifier/field-editor";
import { ApiError, api } from "@/lib/api-client";
import { useProcessingStatus, useVerificationWorkspace } from "@/lib/queries";
import {
  Button, Card, ConfidenceBadge, DocumentStatus, SyntheticNotice, bandFor, useDisplayLanguage,
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
  const { language } = useDisplayLanguage();
  const [selected, setSelected] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState<string | null>(null);

  // A presigned URL for the page on screen, fetched separately so a missing
  // scan does not take the whole workspace down with it (§85). For a PDF this
  // is the rendered page image -- a browser cannot draw the overlay on a PDF.
  const scan = useQuery({
    queryKey: ["document", id, "file", pageNumber],
    retry: false,
    queryFn: () =>
      api.get<{ url: string }>(`/api/v1/documents/${id}/file?page=${pageNumber}`),
  });

  /** Selecting a field opens the page its bbox is on, then zooms to it. */
  function selectField(field: { extraction_id: string; page_number: number }) {
    setSelected(field.extraction_id);
    setPageNumber(field.page_number ?? 1);
  }

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

  // §29 controlled reprocessing -- only offered while no human has worked the
  // document, and the API refuses it after that regardless of what this shows.
  const [confirmRerun, setConfirmRerun] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const rerunProgress = useProcessingStatus(id, rerunning);
  const rerunStatus = rerunProgress.data?.status;
  const rerunFinished = rerunning && (rerunStatus === "SUCCEEDED" || rerunStatus === "FAILED");
  const rerunActive = rerunning && !rerunFinished;

  const rerun = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/documents/${id}/reprocess`, {
        reason: "Re-run from the verification workspace",
      }),
    onMutate: () => {
      setError(null);
      // Drop the previous job's status, or its SUCCEEDED would end this one
      // before it starts.
      queryClient.removeQueries({ queryKey: ["document", id, "status"] });
    },
    onSuccess: () => {
      setConfirmRerun(false);
      setRerunning(true);
    },
    onError: (cause) =>
      setError(cause instanceof ApiError ? cause.message : "Extraction could not be re-run."),
  });

  // When the job finishes, reload the workspace so the new fields appear.
  useEffect(() => {
    if (rerunFinished) refresh();
    // refresh only invalidates queries.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rerunFinished]);

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
        const untouched =
          data.state === "NEEDS_VERIFICATION" &&
          !data.fields.some(
            (f) =>
              f.corrected_value ||
              f.status === "VERIFIER_APPROVED" ||
              f.status === "VERIFIER_CORRECTED",
          );

        const pages = data.pages?.length
          ? data.pages
          : [{ page_number: 1, width: data.page.width, height: data.page.height }];
        const currentPage =
          pages.find((p) => p.page_number === pageNumber) ?? pages[0];
        const onPage = <T extends { page_number?: number }>(items: T[]) =>
          items.filter((item) => (item.page_number ?? 1) === currentPage.page_number);

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
                {untouched || rerunActive ? (
                  <Button
                    variant="outline"
                    busy={rerunActive}
                    disabled={rerunActive}
                    onClick={() => setConfirmRerun(true)}
                  >
                    <RotateCw aria-hidden />
                    {rerunActive ? "Re-running…" : "Re-run extraction"}
                  </Button>
                ) : null}
                <Button
                  busy={submit.isPending}
                  disabled={submitted || rerunActive}
                  onClick={() => submit.mutate()}
                >
                  <Send aria-hidden />
                  {submitted ? "Submitted" : "Submit verification"}
                </Button>
              </div>
            </div>

            {confirmRerun && !rerunActive ? (
              <div
                role="alertdialog"
                aria-label="Confirm re-running extraction"
                className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-navy-100 bg-white px-4 py-3"
              >
                <p className="text-sm text-navy-900">
                  Re-run extraction? Every extracted field on this document is
                  replaced with a fresh result. Nothing has been corrected or
                  accepted yet, so no work is lost.
                </p>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" busy={rerun.isPending} onClick={() => rerun.mutate()}>
                    Re-run
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmRerun(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : null}

            {rerunActive ? (
              <p
                role="status"
                className="mb-4 rounded-card border border-sand-200 bg-sand-50 px-3 py-2 text-sm text-sand-700"
              >
                Re-running extraction
                {rerunProgress.data?.message ? ` — ${rerunProgress.data.message}` : "…"}
                {typeof rerunProgress.data?.progress === "number"
                  ? ` (${rerunProgress.data.progress}%)`
                  : null}
              </p>
            ) : null}

            {rerunFinished ? (
              rerunStatus === "SUCCEEDED" ? (
                <p
                  role="status"
                  className="mb-4 rounded-card border border-high/30 bg-high-bg px-3 py-2 text-sm text-high"
                >
                  Extraction re-run. The fields below are the new results.
                </p>
              ) : (
                <p
                  role="alert"
                  className="mb-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low"
                >
                  Re-running extraction failed: {rerunProgress.data?.error ?? "unknown error"}
                </p>
              )
            ) : null}

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
              <div className="flex flex-col gap-2">
                {pages.length > 1 ? (
                  <nav
                    aria-label="Document pages"
                    className="flex items-center justify-between gap-2 rounded-card border border-sand-200 bg-white px-3 py-1.5"
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={currentPage.page_number <= 1}
                      onClick={() => setPageNumber(currentPage.page_number - 1)}
                    >
                      Previous page
                    </Button>
                    <span className="text-sm text-sand-700">
                      Page{" "}
                      <span className="id font-semibold text-navy-900">
                        {currentPage.page_number}
                      </span>{" "}
                      of {pages.length}
                      <span className="text-sand-500">
                        {" "}
                        · {onPage(data.fields).length} fields here
                      </span>
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={currentPage.page_number >= pages.length}
                      onClick={() => setPageNumber(currentPage.page_number + 1)}
                    >
                      Next page
                    </Button>
                  </nav>
                ) : null}
                <DocumentViewer
                  className={
                    pages.length > 1
                      ? "h-[33rem] lg:h-[calc(100dvh-17rem)]"
                      : "h-[36rem] lg:h-[calc(100dvh-14rem)]"
                  }
                  imageUrl={scan.data?.url ?? null}
                  pageWidth={currentPage.width}
                  pageHeight={currentPage.height}
                  fields={onPage(data.fields)}
                  ocrBlocks={onPage(data.ocr_blocks)}
                  selectedField={selected}
                  onSelectField={setSelected}
                />
              </div>

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
                    {language === "english" ? (
                      <p className="mt-1 text-xs text-sand-500">
                        English readings are for convenience: record terms and
                        place names are translated, people&apos;s names are
                        transliterated and may be spelled differently. The Hindi
                        beside each value is what the page says, and corrections
                        are saved as typed.
                      </p>
                    ) : null}
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
                      onSelect={() => selectField(field)}
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
