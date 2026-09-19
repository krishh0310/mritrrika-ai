import type { HandwritingMeta } from "@/lib/queries";

/**
 * Suspected handwriting, as the reviewer needs it: how much of the page, which
 * fields sit in it, and how trustworthy the scan is. No handwriting is READ —
 * this only says where to look hardest.
 */
export function HandwritingCell({ meta }: { meta: HandwritingMeta | null | undefined }) {
  if (!meta) return <span className="text-xs text-sand-300">none</span>;
  const confidence = meta.confidence ?? 0;
  return (
    <div className="min-w-40 space-y-1.5">
      <span className="inline-flex rounded-chip bg-medium-bg px-1.5 py-0.5 text-xs font-medium text-[#7a5210]">
        {Math.round(meta.coverage_pct * 100)}% handwritten
      </span>
      {meta.affected_fields.length ? (
        <ul className="flex flex-wrap gap-1" aria-label="Fields in handwritten regions">
          {meta.affected_fields.map((field) => (
            <li
              key={field}
              className="rounded-chip border border-sand-200 px-1.5 py-0.5 text-[11px] text-sand-700"
            >
              {field.replaceAll("_", " ")}
            </li>
          ))}
        </ul>
      ) : null}
      <div>
        <div className="flex justify-between text-[11px] text-sand-500">
          <span>Handwriting confidence</span>
          <span className="id">{meta.confidence === null ? "—" : `${Math.round(confidence * 100)}%`}</span>
        </div>
        <div
          className="mt-0.5 h-1.5 overflow-hidden rounded-[2px] bg-sand-100"
          role="img"
          aria-label={`Handwriting confidence ${Math.round(confidence * 100)}%, from scan quality`}
          title="From scan quality (blur, skew, contrast): how far the page itself can be trusted"
        >
          <div className="h-full rounded-[2px] bg-medium" style={{ width: `${confidence * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
