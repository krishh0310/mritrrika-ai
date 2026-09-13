"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AiAssistant } from "@/components/shared/ai-assistant";
import { PageHeader } from "@/components/shell/app-shell";
import {
  LoadingState, useT,
} from "@mrittika/ui";

const SUGGESTIONS = [
  "Show my land parcels.",
  "What is my ownership share in each parcel?",
  "Show the mutation history for my parcels.",
  "Who was the recorded owner in 1998?",
];

/** §18. Authorization happens server-side before retrieval, never after. */
function Assistant() {
  const t = useT();
  const initial = useSearchParams().get("q") ?? undefined;
  return (
    <>
      <PageHeader
        title={t("citizen.assistant.heading")}
        description={t("citizen.assistant.description")}
      />
      <AiAssistant suggestions={SUGGESTIONS} initialQuestion={initial} />
    </>
  );
}

export default function CitizenAssistantPage() {
  const t = useT();
  return (
    <Suspense fallback={<LoadingState label={t("citizen.assistant.loadLabel")} />}>
      <Assistant />
    </Suspense>
  );
}
