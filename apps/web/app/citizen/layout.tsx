"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/citizen/dashboard", labelKey: "citizen.nav.dashboard" },
  { href: "/citizen/my-land", labelKey: "citizen.nav.myLand" },
  { href: "/citizen/map", labelKey: "citizen.nav.map" },
  { href: "/citizen/search", labelKey: "citizen.nav.search" },
  { href: "/citizen/assistant", labelKey: "citizen.nav.assistant" },
  { href: "/citizen/grievances", labelKey: "citizen.nav.grievances" },
];

export default function CitizenLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="CITIZEN" nav={NAV} titleKey="citizen.section.title">
      {children}
    </AppShell>
  );
}
