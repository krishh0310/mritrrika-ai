import { cn } from "./cn";
import { ConfidenceBadge } from "./confidence-badge";

/**
 * The provenance strip — this application's signature element.
 *
 * §26 forbids destroying the raw OCR value during normalization, and §68 says
 * an officer needs raw value, normalized value, confidence and source together
 * to trust anything. Most systems bury that in a tooltip. Here it is the
 * primary rendering of every AI-derived field:
 *
 *     १४२ / २  →  142/2   HIGH 0.95
 *
 * Reading left to right you get what the scanner saw, what the system made of
 * it, and how sure it is — in one line, on every field, on every screen. When
 * a human has corrected the value the strip shows that too, because a
 * correction is provenance as well.
 */

export function ProvenanceStrip({
  raw,
  normalized,
  corrected,
  confidence,
  className,
}: {
  /** Exactly what OCR read, in the original script. Never rewritten. */
  raw: string | null | undefined;
  /** What normalization made of it. */
  normalized: string | null | undefined;
  /** A verifier's correction, if one exists. Wins as the effective value. */
  corrected?: string | null;
  confidence?: number | null;
  className?: string;
}) {
  const machineValue = normalized ?? "—";
  const wasCorrected = corrected !== null && corrected !== undefined && corrected !== "";
  const rawDiffers = raw && raw !== normalized;

  return (
    <span className={cn("provenance", className)}>
      {rawDiffers ? (
        <>
          <span className="provenance-raw" title="Raw OCR — kept unchanged">
            {raw}
          </span>
          <span className="provenance-arrow" aria-hidden>
            →
          </span>
        </>
      ) : null}

      <span
        className={cn(
          "provenance-value",
          wasCorrected && "text-sand-500 line-through decoration-sand-300",
        )}
        title={wasCorrected ? "Model prediction, superseded by a correction" : "Normalized value"}
      >
        {machineValue}
      </span>

      {wasCorrected ? (
        <>
          <span className="provenance-arrow" aria-hidden>
            →
          </span>
          <span
            className="provenance-value font-semibold text-navy-800"
            title="Corrected by a verifier"
          >
            {corrected}
          </span>
        </>
      ) : null}

      {confidence !== undefined ? (
        <ConfidenceBadge score={confidence} className="translate-y-[1px]" />
      ) : null}
    </span>
  );
}

/**
 * The same information stacked, for a form row where the strip must sit under
 * an editable input rather than beside a label.
 */
export function ProvenanceCaption({
  raw,
  normalized,
  modelVersion,
  page,
  className,
}: {
  raw: string | null | undefined;
  normalized: string | null | undefined;
  modelVersion?: string | null;
  page?: number | null;
  className?: string;
}) {
  return (
    <p className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs", className)}>
      <span className="text-sand-500">
        <span className="eyebrow mr-1.5">Raw</span>
        <span className="record-text text-sand-700">{raw || "—"}</span>
      </span>
      <span className="text-sand-500">
        <span className="eyebrow mr-1.5">Normalized</span>
        <span className="id text-sand-700">{normalized || "—"}</span>
      </span>
      {modelVersion ? (
        <span className="text-sand-500">
          <span className="eyebrow mr-1.5">Model</span>
          <span className="id text-sand-700">{modelVersion}</span>
        </span>
      ) : null}
      {page ? (
        <span className="text-sand-500">
          <span className="eyebrow mr-1.5">Page</span>
          <span className="id text-sand-700">{page}</span>
        </span>
      ) : null}
    </p>
  );
}
