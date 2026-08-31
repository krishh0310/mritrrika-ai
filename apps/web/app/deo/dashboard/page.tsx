"use client";

import Link from "next/link";
import {
  CheckCircle2, CircleAlert, Eye, Loader2, Upload, XCircle,
} from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useDeoDashboard } from "@/lib/queries";
import {
  Button, Card, CardHeader, DocumentStatus, EmptyState, QualityVerdict,
  StatCard, Table, Td, Th,
} from "@mrittika/ui";

/** §20 — the operator's own workload, not the whole tehsil's. */
const CARDS = [
  { key: "uploaded_today", label: "Uploaded today", icon: Upload },
  { key: "processing", label: "Processing", icon: Loader2 },
  { key: "completed", label: "Completed", icon: CheckCircle2 },
  { key: "needs_verification", label: "Needs verification", icon: Eye },
  { key: "quality_rejected", label: "Quality rejected", icon: CircleAlert },
  { key: "failed", label: "Failed", icon: XCircle },
] as const;

export default function DeoDashboardPage() {
  const dashboard = useDeoDashboard();

  return (
    <>
      <PageHeader
        title="Digitization"
        description="Documents you have put into the system, and where each one has got to."
        actions={
          <Button asChild>
            <Link href="/deo/upload">
              <Upload aria-hidden />
              Upload a document
            </Link>
          </Button>
        }
      />

      <QueryBoundary query={dashboard} label="your dashboard">
        {(data) => (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
              {CARDS.map(({ key, label, icon: Icon }) => {
                const value = data.cards[key] ?? 0;
                return (
                  <StatCard
                    key={key}
                    label={label}
                    value={value}
                    icon={<Icon className="size-4" />}
                    tone={
                      (key === "failed" || key === "quality_rejected") && value > 0
                        ? "attention"
                        : "default"
                    }
                  />
                );
              })}
            </div>

            <Card className="mt-6">
              <CardHeader
                title="Recent documents"
                description="Your ten most recent uploads."
              />
              {data.recent_documents.length === 0 ? (
                <EmptyState
                  icon={<Upload className="size-7" aria-hidden />}
                  title="You have not uploaded anything yet"
                  description="Scan a Khasra, Khatauni or Jamabandi page and put it through the pipeline."
                  action={
                    <Button asChild size="sm">
                      <Link href="/deo/upload">Upload a document</Link>
                    </Button>
                  }
                />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Document</Th>
                      <Th>Type</Th>
                      <Th>Record year</Th>
                      <Th>State</Th>
                      <Th>Scan quality</Th>
                      <Th className="text-right">Open</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_documents.map((document) => (
                      <tr key={document.document_id} className="hover:bg-sand-50">
                        <Td className="id text-navy-900">{document.document_id}</Td>
                        <Td className="text-sand-700">{document.document_type}</Td>
                        <Td className="id text-sand-700">
                          {document.record_year ?? "—"}
                        </Td>
                        <Td>
                          <DocumentStatus state={document.state} />
                        </Td>
                        <Td>
                          <div className="flex items-center gap-2">
                            <QualityVerdict
                              recommendation={document.quality_recommendation}
                            />
                            {document.quality_score !== null ? (
                              <span className="id text-xs text-sand-500">
                                {document.quality_score.toFixed(2)}
                              </span>
                            ) : null}
                          </div>
                        </Td>
                        <Td className="text-right">
                          <Button asChild variant="link" size="sm">
                            <Link href={`/deo/documents/${document.document_id}`}>
                              Open
                            </Link>
                          </Button>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>
          </>
        )}
      </QueryBoundary>
    </>
  );
}
