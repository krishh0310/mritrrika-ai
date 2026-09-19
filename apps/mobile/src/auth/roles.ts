/**
 * Who the signed-in user is, for rendering purposes only.
 *
 * Mirrors the role vocabulary in apps/web/lib/session.ts. Nothing here confers
 * authority: the stored role decides which navigator to mount, and the server
 * re-derives the real one on every request (§12, §62). Tampering with it
 * changes what a user SEES and never what they may DO.
 */

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

export const ROLES = [
  "CITIZEN", "DEO", "VERIFIER", "TEHSILDAR",
  "STATE_OFFICER", "CENTRAL_OFFICER", "SURVEYOR", "RESEARCHER",
] as const;
export type Role = (typeof ROLES)[number];

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

/**
 * Which mobile experience a user gets (§4).
 *
 * Mobile ships a citizen portal and a field-capture tool, and deliberately not
 * a verification or approval workspace -- §4 says not to recreate the desktop
 * verifier interface on a phone.
 *
 * The capture arm is chosen by PERMISSION, not by role name, because only the
 * DEO role is granted `document:upload`. A verifier or tehsildar is a real
 * person who may well open this app, and routing them to a capture screen on
 * the strength of "not a citizen" would hand them a button that 403s. They get
 * an honest dead end instead, pointing at the desktop where their work lives.
 */
export type Experience = "CITIZEN" | "FIELD" | "DESKTOP_ONLY";

export function experienceFor(user: {
  roles: string[];
  permissions: string[];
}): Experience {
  if (user.roles.includes("CITIZEN")) return "CITIZEN";
  if (user.permissions.includes("document:upload")) return "FIELD";
  return "DESKTOP_ONLY";
}

export function primaryRole(roles: string[]): Role {
  for (const role of ROLES) {
    if (roles.includes(role)) return role;
  }
  return "CITIZEN";
}
