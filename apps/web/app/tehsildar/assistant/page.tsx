"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AiAssistant } from "@/components/shared/ai-assistant";
import { PageHeader } from "@/components/shell/app-shell";
import { LoadingState } from "@mrittika/ui";

/** The §35 questions, verbatim in intent. Each one is answerable server-side. */
const SUGGESTIONS = [
  "Why was this record flagged?",
  "Show low-confidence records for Rampur",
  "Who was the recorded owner of PARCEL-UP-DEMO-0142 in 1998?",
  "Which mutation transferred ownership of khasra 142/2?",
  "Compare current area with historical records for PARCEL-UP-DEMO-0142",
];

/**
 * §35. Scoped to the officer's jurisdiction on the server -- the same
 * predicate the approvals queue and anomaly list use -- so the assistant
 * never sees further than the officer's own screens do.
 */
function Assistant() {
  const initial = useSearchParams().get("q") ?? undefined;
  return (
    <>
      <PageHeader
        title="Records assistant"
        description="Ask about parcels, flags and low-confidence fields in your jurisdiction. Every answer cites the records it used."
      />
      <AiAssistant
        suggestions={SUGGESTIONS}
        initialQuestion={initial}
        placeholder="Ask about records in your jurisdiction…"
      />
    </>
  );
}

export default function TehsildarAssistantPage() {
  return (
    <Suspense fallback={<LoadingState label="the assistant" />}>
      <Assistant />
    </Suspense>
  );
}
