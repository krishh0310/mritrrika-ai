import { cn } from "@mrittika/ui";

/**
 * The record lifecycle, as the landing page's signature element.
 *
 * The numbering here is earned: this genuinely is a sequence, and the order
 * carries information a reader needs — §37 forbids skipping steps, and the
 * whole point of the product is that UPLOADED cannot become APPROVED without
 * passing through every link. Each stage names the role that owns it, because
 * "four roles, strictly separated" is the other half of the thesis.
 */

type Stage = {
  step: string;
  title: string;
  owner: "System" | "DEO" | "Verifier" | "Tehsildar" | "Citizen";
  detail: string;
};

const STAGES: Stage[] = [
  {
    step: "01",
    title: "Capture",
    owner: "DEO",
    detail:
      "A legacy Khasra, Khatauni or Jamabandi page is scanned and tagged with the village and record year it came from.",
  },
  {
    step: "02",
    title: "Quality gate",
    owner: "System",
    detail:
      "Blur, contrast, resolution and skew are measured before any model runs. A page too poor to read is sent back for a rescan, not guessed at.",
  },
  {
    step: "03",
    title: "Read and extract",
    owner: "System",
    detail:
      "Enhancement, OCR, layout parsing and field extraction. Every value keeps its raw text, its bounding box and its own confidence score.",
  },
  {
    step: "04",
    title: "Verify",
    owner: "Verifier",
    detail:
      "A lekhpal works the lowest-confidence fields first. Clicking a field zooms the scan to the region it came from; a correction is stored beside the prediction, never over it.",
  },
  {
    step: "05",
    title: "Approve",
    owner: "Tehsildar",
    detail:
      "The record, the corrections, the ownership history and any flagged inconsistency are reviewed together. Only here does a document become a record of rights.",
  },
  {
    step: "06",
    title: "Consult",
    owner: "Citizen",
    detail:
      "The parcel appears on the holder's dashboard and map. They can trace its mutations, ask a question in plain language, and read the full audit trail.",
  },
];

const OWNER_STYLES: Record<Stage["owner"], string> = {
  System: "bg-sand-100 text-sand-700",
  DEO: "bg-navy-100 text-navy-800",
  Verifier: "bg-medium-bg text-medium",
  Tehsildar: "bg-high-bg text-high",
  Citizen: "bg-cream text-burnt",
};

export function LifecycleChain({ className }: { className?: string }) {
  return (
    <ol className={cn("grid gap-px overflow-hidden rounded-card border border-sand-200 bg-sand-200 md:grid-cols-3", className)}>
      {STAGES.map((stage) => (
        <li key={stage.step} className="relative flex flex-col bg-white p-5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="id text-xs font-semibold text-burnt">
              {stage.step}
            </span>
            <span
              className={cn(
                "rounded-chip px-2 py-0.5 text-[0.6875rem] font-semibold uppercase tracking-wider",
                OWNER_STYLES[stage.owner],
              )}
            >
              {stage.owner}
            </span>
          </div>

          <h3 className="mt-3 text-base font-semibold text-navy-900">{stage.title}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-sand-700">{stage.detail}</p>
        </li>
      ))}
    </ol>
  );
}
