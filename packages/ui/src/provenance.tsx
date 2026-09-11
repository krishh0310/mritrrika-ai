import { cn } from "./cn";
import { ConfidenceBadge } from "./confidence-badge";
import { RecordText, isAscii } from "./record-text";

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
        title={wasCorrected ? "Model prediction, superseded by a correction" : "Standardised value"}
      >
        <RecordText value={normalized} fallback={machineValue} />
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
            <RecordText value={corrected} />
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
  // Identifiers and numbers get the identifier face. Devanagari must not: that
  // face's letter-spacing pulls conjuncts and vowel signs apart, which is how
  // 'डेमो जिला' rendered as 'डेमो   जिला'.
  const valueClass = (value: string | null | undefined) =>
    value && !isAscii(value) ? "record-text text-sand-700" : "id text-sand-700";

  return (
    <p className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs", className)}>
      <span className="text-sand-500" title="Exactly what OCR read, kept unchanged">
        <span className="eyebrow mr-1.5">Read from page</span>
        <span className={valueClass(raw)} lang={raw && !isAscii(raw) ? "hi" : undefined}>
          {raw || "—"}
        </span>
      </span>
      {normalized !== raw ? (
        <span className="text-sand-500" title="The value after digits, units and dates were standardised">
          <span className="eyebrow mr-1.5">Standardised</span>
          <span className={valueClass(normalized)} lang={normalized && !isAscii(normalized) ? "hi" : undefined}>
            {normalized || "—"}
          </span>
        </span>
      ) : null}
      {page ? (
        <span className="text-sand-500">
          <span className="eyebrow mr-1.5">Page</span>
          <span className="id text-sand-700">{page}</span>
        </span>
      ) : null}
      {/* The version is recorded for audit (§64): a correction must trace to
          what produced the value. It is reference detail, not something to
          weigh while verifying, so it trails quietly rather than taking a
          labelled slot of equal weight. */}
      {modelVersion ? (
        <span
          className="ml-auto text-[0.6875rem] text-sand-500"
          title="The extractor version that produced this value, recorded so every correction can be traced to it"
        >
          via {modelVersion}
        </span>
      ) : null}
    </p>
  );
}
