import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { cn } from "./cn";

/**
 * A field's confidence, as a band (§8).
 *
 * Colour alone is never the signal (§86): each band carries its own icon and
 * its own word, so the badge still reads correctly in greyscale, to a
 * colour-blind officer, and to a screen reader.
 */

export const HIGH_THRESHOLD = 0.85;
export const MEDIUM_THRESHOLD = 0.6;

export type ConfidenceBand = "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

export function bandFor(score: number | null | undefined): ConfidenceBand {
  if (score === null || score === undefined || Number.isNaN(score)) return "UNKNOWN";
  if (score >= HIGH_THRESHOLD) return "HIGH";
  if (score >= MEDIUM_THRESHOLD) return "MEDIUM";
  return "LOW";
}

const BAND_STYLES: Record<ConfidenceBand, { chip: string; label: string }> = {
  HIGH: { chip: "bg-high-bg text-high", label: "High" },
  MEDIUM: { chip: "bg-medium-bg text-medium", label: "Medium" },
  LOW: { chip: "bg-low-bg text-low", label: "Low" },
  UNKNOWN: { chip: "bg-sand-100 text-sand-500", label: "Not scored" },
};

const BAND_ICONS: Record<ConfidenceBand, typeof CheckCircle2> = {
  HIGH: CheckCircle2,
  MEDIUM: AlertTriangle,
  LOW: XCircle,
  UNKNOWN: HelpCircle,
};

export function ConfidenceBadge({
  score,
  showScore = true,
  className,
}: {
  score: number | null | undefined;
  /** Hide the number where space is tight; the band word always stays. */
  showScore?: boolean;
  className?: string;
}) {
  const band = bandFor(score);
  const style = BAND_STYLES[band];
  const Icon = BAND_ICONS[band];
  const printed = typeof score === "number" ? score.toFixed(2) : null;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-chip px-1.5 py-0.5",
        "text-[0.6875rem] font-semibold uppercase tracking-wider",
        style.chip,
        className,
      )}
      title={
        printed
          ? `${style.label} confidence — ${printed}`
          : "This field has not been scored"
      }
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      {style.label}
      {showScore && printed ? (
        <span className="id font-normal opacity-80">{printed}</span>
      ) : null}
    </span>
  );
}

/**
 * A confidence bar for dense tables where a badge is too heavy.
 *
 * Still announces the band in text via the accessible label, so it is not a
 * colour-only signal either.
 */
export function ConfidenceBar({
  score,
  className,
}: {
  score: number | null | undefined;
  className?: string;
}) {
  const band = bandFor(score);
  const pct = typeof score === "number" ? Math.round(score * 100) : 0;
  const fill =
    band === "HIGH"
      ? "bg-high"
      : band === "MEDIUM"
        ? "bg-medium"
        : band === "LOW"
          ? "bg-low"
          : "bg-sand-300";

  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        className="h-1.5 w-16 overflow-hidden rounded-full bg-sand-100"
        role="img"
        aria-label={
          typeof score === "number"
            ? `${BAND_STYLES[band].label} confidence, ${pct} percent`
            : "Not scored"
        }
      >
        <span className={cn("block h-full transition-[width]", fill)} style={{ width: `${pct}%` }} />
      </span>
      <span className="id text-xs text-sand-700">
        {typeof score === "number" ? score.toFixed(2) : "—"}
      </span>
    </span>
  );
}
