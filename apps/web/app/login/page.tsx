import { Suspense } from "react";

import { LoginScreen } from "@/components/auth/login-screen";
import { LoadingState } from "@mrittika/ui";

// See: https://nextjs.org/docs/app/guides/migrating-to-cache-components

export const metadata = { title: "Sign in" };

/**
 * Role selection and sign-in (§12, §58).
 *
 * The role cards are navigation. They pre-fill a demo account and change the
 * copy; they confer nothing. The server re-derives the caller's role from
 * their user record on every request, so clicking "Tehsildar" and signing in
 * as a citizen gets you the citizen portal (§12: never trust frontend role
 * selection for security).
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading sign-in" />}>
      <LoginScreen />
    </Suspense>
  );
}
