"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";
import { OVERSIGHT_ROLES } from "@/lib/session";

/**
 * Read-only stakeholders: state and central oversight, the survey department,
 * research institutions. One section, with each link shown only to the roles
 * whose permission the page needs — the server enforces the same rule.
 */
const NAV: NavItem[] = [
  { href: "/oversight/analytics", labelKey: "oversight.nav.analytics", permission: "analytics:view" },
  { href: "/oversight/map", labelKey: "oversight.nav.map", permission: "gis:view" },
  { href: "/oversight/research", labelKey: "oversight.nav.research", permission: "research:export" },
];

export default function OversightLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role={OVERSIGHT_ROLES} nav={NAV} titleKey="oversight.section.title">
      {children}
    </AppShell>
  );
}
