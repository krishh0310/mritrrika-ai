import {
  Archive, CheckCircle2, CircleDashed, ClipboardCheck, Eye, FileScan,
  FileWarning, Gavel, Hourglass, ScanLine, Sparkles, Upload, XCircle,
} from "lucide-react";

import { cn } from "./cn";

/**
 * Status chips for the §37 document state machine and the §19 grievance
 * lifecycle.
 *
 * Each state gets a word, an icon and a colour — in that order of importance.
 * §86: never colour alone. The wording is the user's, not the database's, so
 * NEEDS_VERIFICATION reads "Awaiting verification" rather than shouting an
 * enum at an officer.
 */

type Tone = "neutral" | "progress" | "attention" | "good" | "bad";

const TONE_STYLES: Record<Tone, string> = {
  neutral: "bg-sand-100 text-sand-700",
  progress: "bg-navy-100 text-navy-800",
  attention: "bg-medium-bg text-medium",
  good: "bg-high-bg text-high",
  bad: "bg-low-bg text-low",
};

type StateMeta = { label: string; tone: Tone; icon: typeof CheckCircle2 };

/** §37, in workflow order. */
export const DOCUMENT_STATES: Record<string, StateMeta> = {
  UPLOADED: { label: "Uploaded", tone: "neutral", icon: Upload },
  QUALITY_CHECK: { label: "Checking quality", tone: "progress", icon: ScanLine },
  PROCESSING: { label: "Processing", tone: "progress", icon: Sparkles },
  AI_EXTRACTED: { label: "Extracted", tone: "progress", icon: FileScan },
  NEEDS_VERIFICATION: { label: "Awaiting verification", tone: "attention", icon: Eye },
  UNDER_VERIFICATION: { label: "Being verified", tone: "progress", icon: ClipboardCheck },
  VERIFIED: { label: "Verified", tone: "progress", icon: CheckCircle2 },
  PENDING_APPROVAL: { label: "Awaiting approval", tone: "attention", icon: Hourglass },
  APPROVED: { label: "Approved", tone: "good", icon: Gavel },
  REJECTED: { label: "Rejected", tone: "bad", icon: XCircle },
  RESCAN_REQUIRED: { label: "Rescan needed", tone: "bad", icon: FileWarning },
  ARCHIVED: { label: "Archived", tone: "neutral", icon: Archive },
};

/** §19. */
export const GRIEVANCE_STATES: Record<string, StateMeta> = {
  SUBMITTED: { label: "Submitted", tone: "neutral", icon: Upload },
  UNDER_REVIEW: { label: "Under review", tone: "progress", icon: Eye },
  ACTION_REQUIRED: { label: "Action needed", tone: "attention", icon: FileWarning },
  RESOLVED: { label: "Resolved", tone: "good", icon: CheckCircle2 },
  REJECTED: { label: "Rejected", tone: "bad", icon: XCircle },
};

/** §22 quality gate verdicts. */
export const QUALITY_VERDICTS: Record<string, StateMeta> = {
  PROCESS: { label: "Good to process", tone: "good", icon: CheckCircle2 },
  PROCESS_WITH_WARNING: { label: "Processable, with warnings", tone: "attention", icon: FileWarning },
  RESCAN_RECOMMENDED: { label: "Rescan recommended", tone: "attention", icon: ScanLine },
  REJECT_QUALITY: { label: "Too poor to process", tone: "bad", icon: XCircle },
};

function Chip({ meta, className }: { meta: StateMeta; className?: string }) {
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-chip px-2 py-0.5",
        "text-xs font-medium whitespace-nowrap",
        TONE_STYLES[meta.tone],
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {meta.label}
    </span>
  );
}

function unknown(value: string): StateMeta {
  // Show the raw value rather than "Unknown". If the API grows a state the UI
  // has not learned yet, an officer should see what it actually is.
  return { label: value.replaceAll("_", " ").toLowerCase(), tone: "neutral", icon: CircleDashed };
}

export function DocumentStatus({ state, className }: { state: string; className?: string }) {
  return <Chip meta={DOCUMENT_STATES[state] ?? unknown(state)} className={className} />;
}

export function GrievanceStatus({ status, className }: { status: string; className?: string }) {
  return <Chip meta={GRIEVANCE_STATES[status] ?? unknown(status)} className={className} />;
}

export function QualityVerdict({
  recommendation,
  className,
}: {
  recommendation: string | null | undefined;
  className?: string;
}) {
  if (!recommendation) return null;
  return <Chip meta={QUALITY_VERDICTS[recommendation] ?? unknown(recommendation)} className={className} />;
}

/** Which role is acting. Used in audit timelines and officer headers. */
export function RoleBadge({ role, className }: { role: string; className?: string }) {
  const labels: Record<string, string> = {
    CITIZEN: "Citizen",
    DEO: "Data Entry Operator",
    VERIFIER: "Verifier",
    TEHSILDAR: "Tehsildar",
    STATE_OFFICER: "State Officer",
    CENTRAL_OFFICER: "Central Ministry",
    SURVEYOR: "Survey Department",
    RESEARCHER: "Researcher",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-chip border border-navy-100",
        "bg-white px-2 py-0.5 text-xs font-medium text-navy-800",
        className,
      )}
    >
      {labels[role] ?? role}
    </span>
  );
}

/**
 * The synthetic-data marker (§83).
 *
 * Present on every screen that shows record content. A hackathon prototype
 * must never look like it is exposing real citizens' land.
 */
export function SyntheticNotice({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-chip border border-dashed",
        "border-burnt bg-cream px-2 py-0.5",
        "text-[0.6875rem] font-semibold uppercase tracking-wider text-burnt",
        className,
      )}
    >
      Demo / synthetic data
    </span>
  );
}
