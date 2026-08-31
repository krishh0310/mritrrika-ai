"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/citizen/dashboard", label: "Dashboard" },
  { href: "/citizen/my-land", label: "My land" },
  { href: "/citizen/map", label: "Map" },
  { href: "/citizen/search", label: "Search" },
  { href: "/citizen/assistant", label: "Ask AI" },
  { href: "/citizen/grievances", label: "Grievances" },
];

export default function CitizenLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="CITIZEN" nav={NAV} title="Citizen portal">
      {children}
    </AppShell>
  );
}
