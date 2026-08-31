"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api-client";
import { ErrorState, ForbiddenState, LoadingState } from "@mrittika/ui";

/**
 * The four required states (§85), applied once instead of on every screen.
 *
 * The distinction that matters: a 403 is not an error. §36 refusing a caller
 * is the system working, and telling the user "something went wrong, try
 * again" would send them round a loop that cannot succeed. It gets its own
 * state, with its own wording.
 */
export function QueryBoundary<T>({
  query,
  label,
  children,
  empty,
}: {
  query: UseQueryResult<T>;
  /** What is loading, in the user's words: "your parcels", "the queue". */
  label: string;
  children: (data: T) => ReactNode;
  /** Rendered instead of `children` when the data is present but empty. */
  empty?: { when: (data: T) => boolean; node: ReactNode };
}) {
  if (query.isPending) return <LoadingState label={`Loading ${label}`} />;

  if (query.isError) {
    const error = query.error;

    if (error instanceof ApiError && error.isForbidden) {
      return <ForbiddenState description={error.message} />;
    }

    if (error instanceof ApiError && error.isOffline) {
      return (
        <ErrorState
          title="The Mrittika API is not responding"
          description="Start the API server, then try again. Nothing has been lost."
          onRetry={() => void query.refetch()}
        />
      );
    }

    return (
      <ErrorState
        title={`Could not load ${label}`}
        description={error instanceof Error ? error.message : undefined}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (empty?.when(query.data)) return <>{empty.node}</>;
  return <>{children(query.data)}</>;
}
