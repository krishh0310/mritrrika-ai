"use client";

import { BURNT, ConfidenceSplit, CountBars, toData } from "@/components/tehsildar/charts";
import { LrmsSyncCard, RetrainingPoolCard } from "@/components/tehsildar/operations-cards";
import { ProgressByLocation } from "@/components/tehsildar/progress-by-location";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useAuth } from "@/lib/auth-context";
import { useAnalytics } from "@/lib/queries";
import { Card, CardHeader, DOCUMENT_STATES, SyntheticNotice } from "@mrittika/ui";

/**
 * §31 analytics.
 *
 * Distributions rather than headline numbers — the dashboard already carries
 * the headline figures. What an administrator cannot see from those is where
 * documents are piling up and how the models are doing across the corpus.
 */
export default function AnalyticsPage() {
  const analytics = useAnalytics();
  // The page is shared with the read-only oversight roles; the delivery queue
  // and the retraining pool are the tehsildar's to act on.
  const { can } = useAuth();

  return (
    <>
      <PageHeader
        title="Analytics"
        description={
          can("integration:sync")
            ? "Progress across your jurisdiction, how accurate the models were, and what is flowing to the state LRMS."
            : "Progress across your jurisdiction, and how accurate the models were."
        }
        actions={<SyntheticNotice className="self-center" />}
      />

      <QueryBoundary query={analytics} label="the analytics">
        {(data) => (
          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="lg:col-span-2">
              <CardHeader
                title="Digitization progress by location"
                description="Every level of your jurisdiction, each rolled up from the villages beneath it."
              />
              <ProgressByLocation
                levels={data.progress_by_location.levels}
                rows={data.progress_by_location.rows}
              />
            </Card>

            <Card>
              <CardHeader
                title="Extraction accuracy by field"
                description={
                  data.extraction_accuracy.accuracy === null
                    ? "No verified documents yet."
                    : `${(data.extraction_accuracy.accuracy * 100).toFixed(1)}% of ${data.extraction_accuracy.fields_reviewed} fields kept unchanged by verifiers, across ${data.extraction_accuracy.documents_reviewed} documents.`
                }
              />
              <div className="p-5">
                <CountBars
                  // Sample size in the label: 100% of 3 fields and 100% of 300
                  // are not the same claim.
                  data={data.extraction_accuracy.by_field
                    .filter((row) => row.accuracy !== null)
                    .map((row) => ({
                      name: `${row.field.replaceAll("_", " ").toLowerCase()} (${row.reviewed})`,
                      value: Math.round((row.accuracy ?? 0) * 1000) / 10,
                    }))}
                  unit="% kept unchanged"
                  suffix="%"
                />
                {data.extraction_accuracy.by_model_version.length > 1 ? (
                  <p className="mt-3 border-t border-sand-100 pt-3 text-xs text-sand-500">
                    By model version:{" "}
                    {data.extraction_accuracy.by_model_version
                      .map((v) => `${v.model_version} ${Math.round((v.accuracy ?? 0) * 1000) / 10}%`)
                      .join(" · ")}
                  </p>
                ) : null}
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Documents by workflow state"
                description="Where the corpus is sitting right now."
              />
              <div className="p-5">
                <CountBars
                  data={toData(
                    data.documents_by_state,
                    // The officer's word for the state, not the enum.
                    (key) => DOCUMENT_STATES[key]?.label ?? key.replaceAll("_", " "),
                  )}
                />
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Field confidence"
                description="Every scored field falls in exactly one band."
              />
              <ConfidenceSplit bands={data.confidence_bands} />
            </Card>

            <Card>
              <CardHeader
                title="Documents by record type"
                description="Which legacy forms the corpus is made of."
              />
              <div className="p-5">
                <CountBars data={toData(data.documents_by_type)} />
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Scan quality verdicts"
                description="What the quality gate decided on arrival."
              />
              <div className="p-5">
                <CountBars data={toData(data.documents_by_quality)} />
              </div>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader
                title="Potential inconsistencies by type"
                description="Patterns the checks would question. None is a finding of wrongdoing."
              />
              <div className="p-5">
                <CountBars
                  data={toData(data.anomalies_by_type)}
                  colour={BURNT}
                  unit="flags"
                />
              </div>
            </Card>

            {can("integration:sync") ? <LrmsSyncCard /> : null}
            {can("document:approve") ? <RetrainingPoolCard /> : null}
          </div>
        )}
      </QueryBoundary>
    </>
  );
}
