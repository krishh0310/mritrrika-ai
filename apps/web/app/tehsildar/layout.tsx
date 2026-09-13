"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/tehsildar/dashboard", labelKey: "tehsildar.nav.dashboard" },
  { href: "/tehsildar/approvals", labelKey: "tehsildar.nav.approvals" },
  { href: "/tehsildar/analytics", labelKey: "tehsildar.nav.analytics" },
  { href: "/tehsildar/map", labelKey: "tehsildar.nav.map" },
  { href: "/tehsildar/grievances", labelKey: "tehsildar.nav.grievances" },
  { href: "/tehsildar/assistant", labelKey: "tehsildar.nav.assistant" },
];

export default function TehsildarLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="TEHSILDAR" nav={NAV} titleKey="tehsildar.section.title">
      {children}
    </AppShell>
  );
}
