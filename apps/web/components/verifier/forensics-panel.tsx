"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { api } from "../../lib/api-client";
import { Button, cn, en, useT, type MessageKey } from "@mrittika/ui";

type Report = {
  check: "tamper" | "stamp" | "signature" | "area" | "fraud";
  verdict: string;
  score: number | null;
  result: Record<string, unknown>;
  created_at: string | null;
};

type Translate = (key: MessageKey) => string;

function codeLabel(code: unknown, t: Translate): string {
  const key = `forensics.code.${String(code)}`;
  return Object.hasOwn(en, key) ? t(key as MessageKey) : t("forensics.unknown");
}

function tone(verdict: string) {
  if (verdict === "UNABLE_TO_VERIFY") return "border-sand-300 bg-sand-50 text-sand-700";
  if (["FORGED", "SIGNIFICANT_MISMATCH", "CRITICAL_MISMATCH", "HIGH", "CRITICAL"].includes(verdict)) {
    return "border-low/30 bg-low-bg text-low";
  }
  // Neutral treatment avoids presenting an unvalidated AI result as a certification.
  return "border-sand-300 bg-sand-50 text-sand-700";
}

function highlights(r: Record<string, unknown>, t: Translate): string[] {
  const list = (key: string): Record<string, unknown>[] => Array.isArray(r[key])
    ? r[key].filter((v): v is Record<string, unknown> => !!v && typeof v === "object") : [];
  const strings = (value: unknown): string[] => Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string") : [];
  return [
    r.error && t("forensics.failed"),
    r.explanation,
    ...list("findings").map((f) => `${codeLabel(f.severity, t)}: ${f.issue} (${f.location})`),
    ...list("stamps").filter((s) => s.suspicious).map((s) => `${t("forensics.stampLabel")}: ${s.suspicion_reason}`),
    ...list("signatures").flatMap((s) => strings(s.suspicious_indicators)),
    r.name_match_assessment && `${t("forensics.nameLabel")}: ${codeLabel(r.name_match_assessment, t)}`,
    r.likely_cause && `${t("forensics.causeLabel")}: ${codeLabel(r.likely_cause, t)}`,
    ...list("patterns_detected").map((p) => `${codeLabel(p.severity, t)}: ${p.pattern} — ${p.description}`),
    strings(r.suspicious_entities).length > 0 &&
      `${t("forensics.entitiesLabel")}: ${strings(r.suspicious_entities).join(", ")}`,
    r.recommended_action && `${t("forensics.actionLabel")}: ${codeLabel(r.recommended_action, t)}`,
  ].filter((line): line is string => typeof line === "string" && line.length > 0);
}

/** Advisory provider checks require an explicit, visible external-processing opt-in. */
export function ForensicsPanel({ documentId }: { documentId: string }) {
  const t = useT();
  const [consentDocument, setConsentDocument] = useState<string | null>(null);
  const consent = consentDocument === documentId;
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
    <section aria-label={t("forensics.title")} className="mb-4 rounded-card border border-sand-200 bg-white px-4 py-3">
      <h2 className="text-sm font-semibold text-navy-900">{t("forensics.title")}</h2>
      <p className="mt-2 text-sm text-sand-700">{t("forensics.notice")}</p>
      <label className="my-3 flex items-start gap-2 text-sm text-sand-700">
        <input
          type="checkbox"
          checked={consent}
          disabled={run.isPending}
          onChange={(e) => setConsentDocument(e.target.checked ? documentId : null)}
          className="mt-1 size-4 shrink-0 accent-navy-900"
        />
        {t("forensics.consent")}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        {rows.map((r) => (
          <span key={r.check} className={cn("rounded-chip border px-2 py-0.5 text-xs font-medium", tone(r.verdict))}>
            {t(`forensics.${r.check}`)}: {codeLabel(r.verdict, t)}
            {r.score != null ? ` (${r.score})` : null}
          </span>
        ))}
        <Button
          className="ml-auto" size="sm" variant="outline"
          busy={run.isPending} disabled={!consent || run.isPending}
          onClick={() => { if (consent) run.mutate(); }}
        >
          <ShieldCheck aria-hidden />
          {t(run.isPending ? "forensics.running" : rows.length ? "forensics.rerun" : "forensics.run")}
        </Button>
      </div>
      <p role="status" aria-live="polite" className="mt-2 text-sm text-sand-700">
        {run.isPending ? t("forensics.running") : run.isSuccess ? t("forensics.complete") :
          reports.isLoading ? t("state.loading") : !rows.length && !reports.isError ? t("forensics.empty") : ""}
      </p>
      {reports.isError && (
        <div role="alert" className="mt-2 text-sm text-low">
          <p>{t("forensics.loadFailed")}</p>
          <Button size="sm" variant="outline" onClick={() => reports.refetch()}>{t("state.retry")}</Button>
        </div>
      )}
      {run.isError && <p role="alert" className="mt-2 text-sm text-low">{t("forensics.failed")}</p>}
      {rows.length > 0 && (
        <details className="mt-2 text-sm text-sand-700">
          <summary className="cursor-pointer">{t("forensics.details")}</summary>
          <dl className="mt-2 space-y-2">
            {rows.map((r) => (
              <div key={r.check}>
                <dt className="font-semibold text-navy-900">{t(`forensics.${r.check}`)}</dt>
                {highlights(r.result, t).map((line, i) => <dd key={i} className="ml-3">{line}</dd>)}
              </div>
            ))}
          </dl>
        </details>
      )}
    </section>
  );
}
