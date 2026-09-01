/**
 * The signed-in user, resolved by asking the server.
 *
 * Same rule as the web (apps/web/lib/auth-context.tsx): the current user comes
 * from /auth/me, never from decoding the token on the device. Decoding would
 * let a forged token change what the app shows; asking the server means the
 * answer is always the one the server would enforce (§12).
 *
 * The one mobile-specific part is that reading tokens is asynchronous --
 * SecureStore is a keychain call, not a synchronous storage read -- so
 * `loading` also covers the very first token read, and the navigator must not
 * decide which stack to mount until it clears.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api } from "../api/client";
import { clearTokens, readTokens, writeTokens } from "../storage/session";
import { experienceFor, type CurrentUser, type Experience } from "./roles";

type AuthState = {
  user: CurrentUser | null;
  /** True until the first /auth/me resolves, so the navigator does not flash. */
  loading: boolean;
  experience: Experience | null;
  signIn: (email: string, password: string) => Promise<CurrentUser>;
  signOut: () => Promise<void>;
  /** Convenience for conditional rendering. Never a security decision. */
  can: (permission: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function resolve() {
      if (!(await readTokens())) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const me = await api.get<CurrentUser>("/api/v1/auth/me");
        if (!cancelled) setUser(me);
      } catch (error) {
        // A dead session just means "signed out". Being offline at launch is
        // NOT a dead session -- the tokens stay, so the queue screen still
        // works and /auth/me is retried on the next successful request.
        if (error instanceof ApiError && error.isUnauthenticated) {
          await clearTokens();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void resolve();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const tokens = await api.anonymousPost<{
      access_token: string;
      refresh_token: string;
    }>("/api/v1/auth/login", { email, password });

    await writeTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });

    const me = await api.get<CurrentUser>("/api/v1/auth/me");
    setUser(me);
    return me;
  }, []);

  const signOut = useCallback(async () => {
    const tokens = await readTokens();
    await clearTokens();
    setUser(null);
    if (tokens?.refreshToken) {
      try {
        await api.anonymousPost("/api/v1/auth/logout", {
          refresh_token: tokens.refreshToken,
        });
      } catch {
        // Local sign-out must still succeed while offline.
      }
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      experience: user ? experienceFor(user) : null,
      signIn,
      signOut,
      can: (permission: string) => Boolean(user?.permissions.includes(permission)),
    }),
    [user, loading, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
