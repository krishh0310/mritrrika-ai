"use client";

import { AppShell, type NavItem } from "@/components/shell/app-shell";

const NAV: NavItem[] = [
  { href: "/deo/dashboard", label: "Dashboard" },
  { href: "/deo/upload", label: "Upload" },
];

export default function DeoLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="DEO" nav={NAV} title="Data entry">
      {children}
    </AppShell>
  );
}
