/**
 * Where the browser keeps its tokens.
 *
 * sessionStorage, not localStorage: a token that survives closing the tab is a
 * token that survives walking away from a shared tehsil workstation. It is
 * also not a cookie, because the API is a separate origin using bearer auth
 * and adding a cookie path would mean adding CSRF defence for no gain here.
 *
 * Nothing in this module confers authority. The stored role is used to choose
 * which dashboard to render; the server re-derives the real one on every
 * request (§12, §62), so tampering with it changes what a user SEES and never
 * what they may DO.
 */

const STORAGE_KEY = "mrittika.session";

export type Session = {
  accessToken: string;
  refreshToken: string;
};

export type CurrentUser = {
  user_id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  jurisdiction_id: string | null;
  owner_id: string | null;
  is_synthetic: boolean;
};

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.accessToken !== "string") return null;
    return parsed as Session;
  } catch {
    // Corrupt or storage-blocked. Treat as signed out rather than crashing the
    // whole app on a bad string.
    return null;
  }
}

export function writeSession(session: Session): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Private mode with storage disabled. The session lives for this page load
    // only; the user will be asked to sign in again on navigation.
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
}

/** The roles (§12). Order is the order they appear on the role screen. */
export const ROLES = [
  "CITIZEN", "DEO", "VERIFIER", "TEHSILDAR",
  "STATE_OFFICER", "CENTRAL_OFFICER", "SURVEYOR", "RESEARCHER",
] as const;
export type Role = (typeof ROLES)[number];

/** The read-only stakeholders. They share one section, /oversight. */
export const OVERSIGHT_ROLES = [
  "STATE_OFFICER", "CENTRAL_OFFICER", "SURVEYOR", "RESEARCHER",
] as const satisfies readonly Role[];

export const ROLE_LABELS: Record<Role, string> = {
  CITIZEN: "Citizen",
  DEO: "Data Entry Operator",
  VERIFIER: "Verifier / Lekhpal",
  TEHSILDAR: "Tehsildar",
  STATE_OFFICER: "State Revenue Officer",
  CENTRAL_OFFICER: "Central Ministry Officer",
  SURVEYOR: "Survey Department",
  RESEARCHER: "Research Institution",
};

/** Where each role lands after signing in. */
export const ROLE_HOME: Record<Role, string> = {
  CITIZEN: "/citizen/dashboard",
  DEO: "/deo/dashboard",
  VERIFIER: "/verifier/dashboard",
  TEHSILDAR: "/tehsildar/dashboard",
  STATE_OFFICER: "/oversight/analytics",
  CENTRAL_OFFICER: "/oversight/analytics",
  SURVEYOR: "/oversight/map",
  RESEARCHER: "/oversight/research",
};

/**
 * Pick the landing route for a user.
 *
 * Falls back to the citizen portal rather than throwing: a user with an
 * unrecognised role should see something they can read, not a blank screen.
 */
export function homeFor(roles: string[]): string {
  for (const role of ROLES) {
    if (roles.includes(role)) return ROLE_HOME[role];
  }
  return "/citizen/dashboard";
}
