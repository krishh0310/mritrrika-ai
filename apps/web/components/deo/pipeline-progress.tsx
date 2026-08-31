"use client";

import { Check, CircleDashed, Loader2, X } from "lucide-react";

import type { ProcessingStatus } from "@/lib/queries";
import { cn } from "@mrittika/ui";

/**
 * The §24 stage list, shown as a chain rather than a percentage bar.
 *
 * A bar tells an operator how long is left; the chain tells them what the
 * system is doing to their document, which is the thing that makes the
 * pipeline legible during a demo. The stage names are the API's own, so a new
 * stage appears here without a code change (it lands in the "later" group).
 */

const STAGES = [
  { key: "upload", label: "Upload" },
  { key: "quality", label: "Quality check" },
  { key: "preprocessing", label: "Enhancement" },
  { key: "ocr", label: "Text recognition" },
  { key: "layout", label: "Layout" },
  { key: "extraction", label: "Field extraction" },
  { key: "normalization", label: "Normalization" },
  { key: "validation", label: "Validation" },
  { key: "confidence", label: "Confidence" },
  { key: "complete", label: "Ready for verification" },
] as const;

export function PipelineProgress({ status }: { status: ProcessingStatus }) {
  const currentIndex = STAGES.findIndex((s) => s.key === status.stage);
  const failed = status.status === "FAILED";
  const done = status.status === "SUCCEEDED";

  return (
    <div>
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <p className="text-sm text-sand-700">
          {failed
            ? "Processing stopped"
            : done
              ? "Processing finished"
              : (status.message ?? "Working…")}
        </p>
        <span className="id text-sm text-sand-500">{status.progress}%</span>
      </div>

      <div
        className="mb-5 h-1.5 overflow-hidden rounded-full bg-sand-100"
        role="progressbar"
        aria-valuenow={status.progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Processing progress"
      >
        <div
          className={cn(
            "h-full transition-[width] duration-500",
            failed ? "bg-low" : done ? "bg-high" : "bg-burnt",
          )}
          style={{ width: `${status.progress}%` }}
        />
      </div>

      <ol className="space-y-1">
        {STAGES.map((stage, index) => {
          const reached = done || (currentIndex >= 0 && index < currentIndex);
          const active = !done && !failed && index === currentIndex;
          const stopped = failed && index === currentIndex;

          return (
            <li
              key={stage.key}
              className={cn(
                "flex items-center gap-2.5 rounded-chip px-2 py-1.5 text-sm",
                active && "bg-cream",
                stopped && "bg-low-bg",
              )}
            >
              <span className="flex size-4 shrink-0 items-center justify-center">
                {stopped ? (
                  <X className="size-4 text-low" aria-hidden />
                ) : reached ? (
                  <Check className="size-4 text-high" aria-hidden />
                ) : active ? (
                  <Loader2 className="size-4 animate-spin text-burnt" aria-hidden />
                ) : (
                  <CircleDashed className="size-3.5 text-sand-300" aria-hidden />
                )}
              </span>
              <span
                className={cn(
                  reached
                    ? "text-sand-700"
                    : active || stopped
                      ? "font-medium text-navy-900"
                      : "text-sand-300",
                )}
              >
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>

      {status.error ? (
        <p className="mt-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low">
          {status.error}
        </p>
      ) : null}
    </div>
  );
}
