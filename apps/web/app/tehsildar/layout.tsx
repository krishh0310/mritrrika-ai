"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/tehsildar/dashboard", label: "Dashboard" },
  { href: "/tehsildar/approvals", label: "Approvals" },
  { href: "/tehsildar/analytics", label: "Analytics" },
  { href: "/tehsildar/map", label: "Map" },
  { href: "/tehsildar/grievances", label: "Grievances" },
];

export default function TehsildarLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="TEHSILDAR" nav={NAV} title="Tehsildar">
      {children}
    </AppShell>
  );
}
