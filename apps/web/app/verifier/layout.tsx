"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/verifier/dashboard", labelKey: "verifier.nav.dashboard" },
  { href: "/verifier/queue", labelKey: "verifier.nav.queue" },
];

export default function VerifierLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="VERIFIER" nav={NAV} titleKey="verifier.section.title">
      {children}
    </AppShell>
  );
}
