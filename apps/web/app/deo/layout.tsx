"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/deo/dashboard", labelKey: "deo.nav.dashboard" },
  { href: "/deo/upload", labelKey: "deo.nav.upload" },
  { href: "/deo/bulk", labelKey: "deo.nav.bulk" },
];

export default function DeoLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="DEO" nav={NAV} titleKey="deo.section.title">
      {children}
    </AppShell>
  );
}
