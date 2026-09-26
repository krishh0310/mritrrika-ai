"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { ApiError, api } from "@/lib/api-client";
import { Button, cn } from "@mrittika/ui";

type Report = {
  check: "tamper" | "stamp" | "signature" | "area" | "fraud";
  verdict: string;
  score: number | null;
  result: Record<string, unknown>;
  created_at: string | null;
};

const LABEL: Record<Report["check"], string> = {
  tamper: "Tampering",
  stamp: "Stamps & seals",
  signature: "Signatures",
  area: "Area vs map",
  fraud: "Transaction history",
};

const GOOD = new Set(["AUTHENTIC", "WITHIN_TOLERANCE", "LOW"]);
const BAD = new Set(["FORGED", "SIGNIFICANT_MISMATCH", "CRITICAL_MISMATCH", "HIGH", "CRITICAL"]);

function tone(verdict: string) {
  if (verdict === "UNABLE_TO_VERIFY") return "border-sand-300 bg-sand-50 text-sand-700";
  if (GOOD.has(verdict)) return "border-high/30 bg-high-bg text-high";
  if (BAD.has(verdict)) return "border-low/30 bg-low-bg text-low";
  return "border-medium/40 bg-medium-bg text-[#7a5210]";
}

/** The human-readable lines out of each check's JSON. */
function highlights(r: Record<string, unknown>): string[] {
  const list = (key: string) => (Array.isArray(r[key]) ? (r[key] as Record<string, unknown>[]) : []);
  return [
    r.error && `Could not run: ${r.error}`,
    r.explanation,
    ...list("findings").map((f) => `${f.severity}: ${f.issue} (${f.location})`),
    ...list("stamps").filter((s) => s.suspicious).map((s) => `Stamp: ${s.suspicion_reason}`),
    ...list("signatures").flatMap((s) => (s.suspicious_indicators as string[]) ?? []),
    r.name_match_assessment && `Name match: ${r.name_match_assessment}`,
    r.likely_cause && `Likely cause: ${r.likely_cause}`,
    ...list("patterns_detected").map((p) => `${p.severity}: ${p.pattern} — ${p.description}`),
    (r.suspicious_entities as string[] | undefined)?.length &&
      `Investigate: ${(r.suspicious_entities as string[]).join(", ")}`,
    r.recommended_action && `Recommended: ${r.recommended_action}`,
  ].filter((line): line is string => typeof line === "string" && line.length > 0);
}

/**
 * Gemini forensic checks (advisory). Run on demand because each run sends
 * the scan to Google; results are leads for the verifier, not findings.
 */
export function ForensicsPanel({ documentId }: { documentId: string }) {
  const queryClient = useQueryClient();
  const key = ["document", documentId, "forensics"];
  const reports = useQuery({
    queryKey: key,
    queryFn: () => api.get<{ reports: Report[] }>(`/api/v1/documents/${documentId}/forensics`),
  });
  const run = useMutation({
    mutationFn: () => api.post<{ reports: Report[] }>(`/api/v1/documents/${documentId}/forensics`, {}),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
  const rows = reports.data?.reports ?? [];

  return (
    <section
      aria-label="Forensic checks"
      className="mb-4 rounded-card border border-sand-200 bg-white px-4 py-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-1 text-sm font-semibold text-navy-900">Forensic checks</h2>
        {rows.map((r) => (
          <span
            key={r.check}
            className={cn("rounded-chip border px-2 py-0.5 text-xs font-medium", tone(r.verdict))}
          >
            {LABEL[r.check]}: {r.verdict.replaceAll("_", " ").toLowerCase()}
            {r.score != null ? ` (${r.score})` : null}
          </span>
        ))}
        {rows.length === 0 && !reports.isLoading ? (
          <span className="text-xs text-sand-500">Not run yet.</span>
        ) : null}
        <Button
          className="ml-auto"
          size="sm"
          variant="outline"
          busy={run.isPending}
          disabled={run.isPending}
          onClick={() => run.mutate()}
        >
          <ShieldCheck aria-hidden />
          {run.isPending ? "Checking…" : rows.length ? "Re-run checks" : "Run checks"}
        </Button>
      </div>

      {run.isError ? (
        <p role="alert" className="mt-2 text-xs text-low">
          {run.error instanceof ApiError ? run.error.message : "The checks could not be run."}
        </p>
      ) : null}

      {rows.length ? (
        <details className="mt-2 text-xs text-sand-700">
          <summary className="cursor-pointer text-sand-500">
            Details (AI-generated, advisory — confirm before acting)
          </summary>
          <dl className="mt-2 space-y-2">
            {rows.map((r) => (
              <div key={r.check}>
                <dt className="font-semibold text-navy-900">{LABEL[r.check]}</dt>
                {highlights(r.result).map((line, i) => (
                  <dd key={i} className="ml-3">{line}</dd>
                ))}
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </section>
  );
}
