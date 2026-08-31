"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/lib/api-client";
import { AuthProvider } from "@/lib/auth-context";

/**
 * Client-side providers.
 *
 * The retry policy is the part worth reading: a 401/403/404 is an answer, not
 * a failure. Retrying a 403 three times just delays telling the user they are
 * not permitted, and retrying a 401 fights the refresh logic in api-client.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              if (error instanceof ApiError) {
                if (error.status === 401 || error.status === 403 || error.status === 404) {
                  return false;
                }
              }
              return failureCount < 2;
            },
          },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
