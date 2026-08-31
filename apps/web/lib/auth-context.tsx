"use client";

/**
 * Who is signed in, for rendering purposes only.
 *
 * The context resolves the current user by calling /auth/me rather than by
 * decoding the token client-side. Decoding would let a forged token change
 * what the UI shows; asking the server means the answer is always the one the
 * server would enforce (§12).
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

import { api, ApiError } from "./api-client";
import {
  clearSession,
  readSession,
  writeSession,
  type CurrentUser,
} from "./session";

type AuthState = {
  user: CurrentUser | null;
  /** True until the first /auth/me resolves, so guards do not flash. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<CurrentUser>;
  signOut: () => void;
  /** Convenience for conditional rendering. Never a security decision. */
  can: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function resolve() {
      if (!readSession()) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const me = await api.get<CurrentUser>("/api/v1/auth/me");
        if (!cancelled) setUser(me);
      } catch (error) {
        // A dead session is not an error worth surfacing; it just means
        // "signed out". Anything else is left for the screen to report.
        if (error instanceof ApiError && error.isUnauthenticated) clearSession();
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

    writeSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });

    const me = await api.get<CurrentUser>("/api/v1/auth/me");
    setUser(me);
    return me;
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn,
      signOut,
      can: (permission) => user?.permissions.includes(permission) ?? false,
      hasRole: (role) => user?.roles.includes(role) ?? false,
    }),
    [user, loading, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
