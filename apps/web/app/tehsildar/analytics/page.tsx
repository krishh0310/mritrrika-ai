"use client";

import { BURNT, ConfidenceSplit, CountBars, toData } from "@/components/tehsildar/charts";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
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

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Where documents are, how they were scanned, and how confident the models were."
        actions={<SyntheticNotice className="self-center" />}
      />

      <QueryBoundary query={analytics} label="the analytics">
        {(data) => (
          <div className="grid gap-5 lg:grid-cols-2">
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
          </div>
        )}
      </QueryBoundary>
    </>
  );
}
