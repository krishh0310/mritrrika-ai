"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { ArrowLeft, Play } from "lucide-react";

import { PipelineProgress } from "@/components/deo/pipeline-progress";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { TranslatedBadge } from "@/components/shared/translated-badge";
import { PageHeader } from "@/components/shell/app-shell";
import { ApiError, api } from "@/lib/api-client";
import { useDocument, useProcessingStatus, type Quality } from "@/lib/queries";
import {
  Button, Card, CardHeader, ConfidenceBar, DocumentStatus, QualityVerdict,
} from "@mrittika/ui";

/**
 * One document, from the operator's side (§22, §23, §24).
 *
 * The quality report is shown in full, including the individual measurements,
 * because a "rescan recommended" verdict is only actionable if the operator
 * can see it was the blur and not the lighting.
 */
export default function DeoDocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const document = useDocument(id);
  const state = document.data?.state;

  // §37: the legal move into the pipeline is QUALITY_CHECK -> PROCESSING, and
  // upload leaves a document in QUALITY_CHECK. UPLOADED is accepted too, for
  // a document whose quality gate has not run yet.
  const canStart = state === "QUALITY_CHECK" || state === "UPLOADED";
  const isLive = canStart || state === "PROCESSING";
  const status = useProcessingStatus(id, Boolean(state) && !canStart);

  const start = useMutation({
    // synchronous=true runs the same pipeline inline. It exists so the demo
    // works on a machine with no Celery worker running -- it is not a mock.
    mutationFn: () =>
      api.post(`/api/v1/documents/${id}/process?synchronous=true`, {}),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["document", id] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError ? cause.message : "Processing could not start.",
      ),
  });

  return (
    <>
      <Button asChild variant="link" size="sm" className="mb-2 -ml-3">
        <Link href="/deo/dashboard">
          <ArrowLeft aria-hidden />
          Back to dashboard
        </Link>
      </Button>

      <QueryBoundary query={document} label="the document">
        {(data) => (
          <>
            <PageHeader
              title={data.document_id}
              description={
                <>
                  {data.document_type.replaceAll("_", " ")}
                  {data.record_year ? ` · record year ${data.record_year}` : ""}
                  {data.original_filename ? ` · ${data.original_filename}` : ""}
                </>
              }
              actions={
                <>
                  <TranslatedBadge from={data.translated_from} />
                  <DocumentStatus state={data.state} className="self-center" />
                  {canStart ? (
                    <Button busy={start.isPending} onClick={() => start.mutate()}>
                      <Play aria-hidden />
                      Start processing
                    </Button>
                  ) : null}
                  {data.state === "NEEDS_VERIFICATION" ? (
                    <Button asChild variant="outline">
                      <Link href={`/verifier/documents/${data.document_id}`}>
                        Open in verification
                      </Link>
                    </Button>
                  ) : null}
                </>
              }
            />

            {error ? (
              <p
                role="alert"
                className="mb-5 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low"
              >
                {error}
              </p>
            ) : null}

            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader
                  title="Scan quality"
                  description="Measured on arrival, before any model runs."
                  action={
                    <QualityVerdict recommendation={data.quality_recommendation} />
                  }
                />
                <div className="p-5">
                  {data.quality_report ? (
                    <QualityReport
                      report={data.quality_report as unknown as Quality}
                      overall={data.quality_score}
                    />
                  ) : (
                    <p className="text-sm text-sand-500">
                      No quality report on file for this document.
                    </p>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Pipeline"
                  description={
                    isLive
                      ? "Updating as the document moves through each stage."
                      : "What the document has been through."
                  }
                />
                <div className="p-5">
                  {status.data ? (
                    <PipelineProgress status={status.data} />
                  ) : data.quality_recommendation === "REJECT_QUALITY" ? (
                    <p className="text-sm text-sand-700">
                      This scan is too poor to read reliably. Rescan the page
                      before putting it through the pipeline.
                    </p>
                  ) : (
                    <p className="text-sm text-sand-500">
                      Processing has not started. Use “Start processing” above.
                    </p>
                  )}
                </div>
              </Card>
            </div>
          </>
        )}
      </QueryBoundary>
    </>
  );
}

/** Each measurement, so a poor verdict points at what to fix. */
function QualityReport({
  report,
  overall,
}: {
  report: Quality;
  overall: number | null;
}) {
  const measures: [string, number | null][] = [
    ["Sharpness", report.blur_score ?? null],
    ["Contrast", report.contrast_score ?? null],
    ["Resolution", report.resolution_score ?? null],
    ["Straightness", report.skew_score ?? null],
    ["Brightness", report.brightness_score ?? null],
  ];

  return (
    <dl className="space-y-3">
      {measures.map(([label, score]) => (
        <div key={label} className="flex items-center justify-between gap-4">
          <dt className="text-sm text-sand-700">{label}</dt>
          <dd>
            <ConfidenceBar score={score} />
          </dd>
        </div>
      ))}

      <div className="flex items-center justify-between gap-4 border-t border-sand-200 pt-3">
        <dt className="text-sm font-medium text-navy-900">Overall</dt>
        <dd>
          <ConfidenceBar score={overall} />
        </dd>
      </div>

      {report.skew_angle !== undefined && report.skew_angle !== null ? (
        <p className="pt-1 text-xs text-sand-500">
          Page is rotated{" "}
          <span className="id">{report.skew_angle.toFixed(1)}°</span> from square.
        </p>
      ) : null}
    </dl>
  );
}
