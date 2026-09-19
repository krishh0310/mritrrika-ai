"use client";

import { useState } from "react";
import { Download } from "lucide-react";

import { PageHeader } from "@/components/shell/app-shell";
import { api } from "@/lib/api-client";
import { Button, Card, CardHeader, SyntheticNotice } from "@mrittika/ui";

const COLUMNS = [
  ["state, district, tehsil, village", "where the parcel is — never the plot itself"],
  ["area_sqm", "rounded to 100 m², so it cannot be matched to a recorded figure"],
  ["land_class", "as recorded"],
  ["current_holders, mutations, last_mutation_year", "how the holding has changed"],
  ["digitized", "whether an approved digital record exists"],
];

/** §15 — anonymised parcel data for research institutions. */
export default function ResearchPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const csv = await api.text("/api/v1/research/export.csv");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const link = Object.assign(document.createElement("a"), {
        href: url,
        download: "mrittika-parcels-anonymised.csv",
      });
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Research data"
        description="One row per parcel in your jurisdiction, with nothing that names a person or a plot."
        actions={<SyntheticNotice className="self-center" />}
      />
      <Card className="max-w-3xl">
        <CardHeader
          title="Anonymised parcel export (CSV)"
          description="Owner names, parcel ids, khasra and khata numbers and geometry are removed. Every export is recorded in the audit trail."
          action={
            <Button busy={busy} onClick={download}>
              <Download className="size-4" aria-hidden />
              Download CSV
            </Button>
          }
        />
        <dl className="divide-y divide-sand-100">
          {COLUMNS.map(([name, meaning]) => (
            <div key={name} className="grid gap-1 px-5 py-3 sm:grid-cols-[16rem_1fr]">
              <dt className="id text-sm text-navy-900">{name}</dt>
              <dd className="text-sm text-sand-700">{meaning}</dd>
            </div>
          ))}
        </dl>
        {error ? (
          <p className="mx-5 mb-4 rounded-card bg-low-bg px-3 py-2 text-sm text-low" role="alert">
            {error}
          </p>
        ) : null}
      </Card>
    </>
  );
}
