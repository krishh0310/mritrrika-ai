"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/verifier/dashboard", label: "Dashboard" },
  { href: "/verifier/queue", label: "Queue" },
];

export default function VerifierLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="VERIFIER" nav={NAV} title="Verification">
      {children}
    </AppShell>
  );
}
