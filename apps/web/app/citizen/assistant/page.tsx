"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AiAssistant } from "@/components/shared/ai-assistant";
import { PageHeader } from "@/components/shell/app-shell";
import { LoadingState } from "@mrittika/ui";

const SUGGESTIONS = [
  "Show my land parcels.",
  "What is my ownership share in each parcel?",
  "Show the mutation history for my parcels.",
  "Who was the recorded owner in 1998?",
];

/** §18. Authorization happens server-side before retrieval, never after. */
function Assistant() {
  const initial = useSearchParams().get("q") ?? undefined;
  return (
    <>
      <PageHeader
        title="Ask about your records"
        description="The assistant can only reach records you are already entitled to see, and cites what it used."
      />
      <AiAssistant suggestions={SUGGESTIONS} initialQuestion={initial} />
    </>
  );
}

export default function CitizenAssistantPage() {
  return (
    <Suspense fallback={<LoadingState label="the assistant" />}>
      <Assistant />
    </Suspense>
  );
}
