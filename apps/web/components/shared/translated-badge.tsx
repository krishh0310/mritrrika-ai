const LANGUAGE: Record<string, string> = {
  ben: "Bengali",
  guj: "Gujarati",
  pan: "Punjabi",
  ori: "Odia",
  mal: "Malayalam",
};

/**
 * Fields on this document came from translating the page to Hindi. Values
 * such as names are renderings, not what the page says — so say so.
 */
export function TranslatedBadge({ from }: { from: string | null | undefined }) {
  if (!from) return null;
  return (
    <span className="inline-flex items-center self-center rounded-chip border border-medium/40 bg-medium-bg px-2 py-0.5 text-xs font-medium text-[#7a5210]">
      Translated from {LANGUAGE[from] ?? from} (verify carefully)
    </span>
  );
}
