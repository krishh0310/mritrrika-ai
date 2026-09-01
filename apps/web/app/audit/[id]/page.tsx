"use client";

import Link from "next/link";
import { use, useState } from "react";
import { ArrowLeft, Link2, ShieldCheck, ShieldX } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { useAuditChain, useAuditTrail, type AuditEvent } from "@/lib/queries";
import {
  Button, Card, CardHeader, ForbiddenState, LoadingState, RoleBadge,
  SyntheticNotice, cn,
} from "@mrittika/ui";

/**
 * §41 — the audit trail for one document, and the chain check.
 *
 * Two deliberate choices in the wording:
 *
 *   * "Hash chain", never "blockchain" (§41 says so explicitly). What it is:
 *     each event carries a SHA-256 over its own contents plus the previous
 *     event's hash, so altering any past event breaks every hash after it.
 *   * "Verify the chain" reports what was checked and what was found, rather
 *     than flashing a green tick. A verification nobody can inspect is
 *     theatre.
 */

/** The action names, in the words an officer reads. */
const ACTION_LABELS: Record<string, string> = {
  "document.upload": "Document uploaded",
  "document.quality_check": "Scan quality assessed",
  "document.processing_started": "AI processing started",
  "document.processing_completed": "AI processing finished",
  "document.processing_failed": "AI processing failed",
  "extraction.corrected": "Field corrected by a verifier",
  "document.verified": "Verification submitted",
  "document.approved": "Approved as the record of rights",
  "document.rejected": "Rejected",
  "document.returned": "Returned to the verifier",
  "document.state_changed": "State changed",
  "document.download": "Document downloaded",
  "grievance.created": "Grievance raised",
  "grievance.status_changed": "Grievance status changed",
  "anomaly.verdict": "Officer ruled on a flag",
  "auth.login": "Signed in",
};

export default function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, loading } = useAuth();
  const [checking, setChecking] = useState(false);

  const trail = useAuditTrail(id);
  const chain = useAuditChain(checking);

  if (loading) return <LoadingState label="Checking your session" />;

  if (!user) {
    return (
      <main id="main" className="mx-auto max-w-2xl px-6 py-20">
        <ForbiddenState description="Sign in to read an audit trail." />
        <div className="flex justify-center">
          <Button asChild variant="outline">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main id="main" className="mx-auto max-w-4xl px-6 py-8">
      <Button asChild variant="link" size="sm" className="mb-2 -ml-3">
        <Link href="/">
          <ArrowLeft aria-hidden />
          Mrittika AI
        </Link>
      </Button>

      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Audit trail</p>
          <h1 className="id mt-1 text-2xl font-semibold text-navy-900">{id}</h1>
          <p className="mt-1 max-w-2xl text-sm text-sand-700">
            Every sensitive action, in order, each hashed together with the one
            before it. Altering a past entry would break every hash after it.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SyntheticNotice />
          <Button variant="outline" onClick={() => setChecking(true)} busy={chain.isFetching}>
            <ShieldCheck aria-hidden />
            Verify the chain
          </Button>
        </div>
      </div>

      {checking ? (
        <Card className="mb-5">
          {chain.isPending ? (
            <LoadingState label="Recomputing every hash" />
          ) : chain.isError ? (
            <p className="px-5 py-4 text-sm text-low">
              {chain.error instanceof ApiError
                ? chain.error.message
                : "The chain could not be checked."}
            </p>
          ) : chain.data ? (
            <div
              className={cn(
                "flex items-start gap-3 px-5 py-4",
                chain.data.valid ? "bg-high-bg" : "bg-low-bg",
              )}
            >
              {chain.data.valid ? (
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-high" aria-hidden />
              ) : (
                <ShieldX className="mt-0.5 size-5 shrink-0 text-low" aria-hidden />
              )}
              <div>
                <p
                  className={cn(
                    "text-sm font-medium",
                    chain.data.valid ? "text-high" : "text-low",
                  )}
                >
                  {chain.data.valid
                    ? "The chain is intact"
                    : "The chain does not verify"}
                </p>
                <p className="mt-0.5 text-sm text-sand-700">
                  Recomputed <span className="id">{chain.data.events}</span> events
                  using {chain.data.mechanism}.
                  {chain.data.problems.length > 0
                    ? ` Problems: ${chain.data.problems.join("; ")}`
                    : " No entry has been altered since it was written."}
                </p>
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Events"
          description="Oldest first, as they happened."
        />
        <QueryBoundary query={trail} label="the audit trail">
          {(data) => (
            <ol className="divide-y divide-sand-100">
              {data.events.map((event) => (
                <AuditRow key={event.sequence} event={event} />
              ))}
            </ol>
          )}
        </QueryBoundary>
      </Card>
    </main>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const changed = event.before_state || event.after_state;

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="id text-xs text-sand-300">#{event.sequence}</span>
        <span className="text-sm font-medium text-navy-900">
          {ACTION_LABELS[event.action] ?? event.action}
        </span>
        {event.actor_role ? <RoleBadge role={event.actor_role} /> : null}
        <span className="id ml-auto text-xs text-sand-500">
          {event.timestamp.slice(0, 19).replace("T", " ")}
        </span>
      </div>

      {event.reason ? (
        <p className="mt-1.5 text-sm text-sand-700">
          <span className="eyebrow mr-1.5">Reason</span>
          {event.reason}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <span
          className="id flex items-center gap-1.5 text-xs text-sand-300"
          title={`This event's hash: ${event.event_hash}`}
        >
          <Link2 className="size-3" aria-hidden />
          {event.event_hash.slice(0, 16)}…
        </span>
        {changed ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="text-xs text-navy-700 underline-offset-2 hover:underline"
          >
            {open ? "Hide what changed" : "Show what changed"}
          </button>
        ) : null}
      </div>

      {open && changed ? (
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {event.before_state ? (
            <StatePanel title="Before" state={event.before_state} />
          ) : null}
          {event.after_state ? (
            <StatePanel title="After" state={event.after_state} />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function StatePanel({
  title,
  state,
}: {
  title: string;
  state: Record<string, unknown>;
}) {
  return (
    <div className="rounded-card border border-sand-200 bg-sand-50 p-3">
      <p className="eyebrow mb-1.5">{title}</p>
      <dl className="space-y-1">
        {Object.entries(state).map(([key, value]) => (
          <div key={key} className="flex gap-2 text-xs">
            <dt className="shrink-0 text-sand-500">{key.replaceAll("_", " ")}</dt>
            <dd className="id break-all text-sand-700">
              {typeof value === "object" && value !== null
                ? JSON.stringify(value)
                : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
