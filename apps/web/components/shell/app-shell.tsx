"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, type ReactNode } from "react";
import { LogOut } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useLocations } from "@/lib/queries";
import { ROLE_LABELS, type Role } from "@/lib/session";
import {
  Button, DisplayLanguageProvider, DisplayLanguageToggle, ForbiddenState, LoadingState,
  RoleBadge, SyntheticNotice, UiLanguageProvider, UiLanguageToggle, cn, useT,
  type MessageKey, type UiLanguage,
} from "@mrittika/ui";

/**
 * The chrome every signed-in screen sits in, plus the client-side guard.
 *
 * The guard is a convenience, not a security boundary: it saves a citizen from
 * loading the tehsildar's dashboard only to watch every request 403. The
 * boundary itself is the API (§36), which is why each screen still renders
 * whatever the server returns rather than assuming the guard let the right
 * person through.
 */

/**
 * Nav items carry a message KEY, not a label. A literal string here would be
 * a piece of chrome that the language toggle cannot reach -- and navigation is
 * the first thing a reader needs in their own language.
 */
export type NavItem = { href: string; labelKey: MessageKey };

/**
 * What each role reads before anyone chooses.
 *
 * Citizens default to Hindi: the portal is public-facing and the records
 * themselves are in Hindi. Officers default to English, which is the revenue
 * service's working language and what every internal screen, export and audit
 * entry is already written in. A stored choice always overrides this -- the
 * default is a starting point, not a statement about what someone can read.
 */
const DEFAULT_LANGUAGE: Record<Role, UiLanguage> = {
  CITIZEN: "hi",
  DEO: "en",
  VERIFIER: "en",
  TEHSILDAR: "en",
};

export function AppShell({
  role,
  nav,
  titleKey,
  children,
}: {
  /** The role this section belongs to. Used for the guard and the header. */
  role: Role;
  nav: NavItem[];
  /** Message key for the section name, so the header speaks the chosen language. */
  titleKey: MessageKey;
  children: ReactNode;
}) {
  const { user, loading, signOut, hasRole } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // Official English place names, so the English view says "Mudiyakala"
  // rather than a machine transliteration of मुड़ियाकला. Every role holds
  // gis:view; if the list cannot load, names fall back to transliteration.
  const locations = useLocations(undefined, { enabled: Boolean(user) });
  const places = useMemo(() => {
    const map: Record<string, string> = {};
    for (const location of locations.data?.locations ?? []) {
      if (location.name_devanagari) map[location.name_devanagari] = location.name;
    }
    return map;
  }, [locations.data]);

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?role=${role}&next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, router, role, pathname]);

  if (loading) return <LoadingState label="Checking your session" />;
  if (!user) return <LoadingState label="Redirecting to sign in" />;

  if (!hasRole(role)) {
    return (
      <main id="main" className="mx-auto max-w-2xl px-6 py-20">
        <ForbiddenState
          description={`This section is for the ${ROLE_LABELS[role]} role. You are signed in as ${user.roles.map((r) => ROLE_LABELS[r as Role] ?? r).join(", ")}.`}
        />
        <div className="flex justify-center">
          <Button variant="outline" onClick={signOut}>
            Sign in as someone else
          </Button>
        </div>
      </main>
    );
  }

  // The chrome is a separate component because `useT` reads the provider, and
  // a hook cannot see a context its own component renders.
  return (
    <UiLanguageProvider defaultLanguage={DEFAULT_LANGUAGE[role] ?? "en"}>
      <DisplayLanguageProvider places={places}>
        <ShellChrome
          role={role}
          nav={nav}
          titleKey={titleKey}
          pathname={pathname}
          userName={user.full_name}
          onSignOut={() => {
            signOut();
            router.replace("/login");
          }}
        >
          {children}
        </ShellChrome>
      </DisplayLanguageProvider>
    </UiLanguageProvider>
  );
}

function ShellChrome({
  role,
  nav,
  titleKey,
  pathname,
  userName,
  onSignOut,
  children,
}: {
  role: Role;
  nav: NavItem[];
  titleKey: MessageKey;
  pathname: string;
  userName: string;
  onSignOut: () => void;
  children: ReactNode;
}) {
  const t = useT();

  return (
    <div className="min-h-dvh bg-offwhite">
      <header className="border-b border-navy-700 bg-navy-900 text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-3 px-5 py-3">
          <Link href="/" className="text-base font-semibold tracking-tight">
            {t("app.name")}
          </Link>
          <span className="text-sm text-navy-300">{t(titleKey)}</span>
          <SyntheticNotice className="border-warm text-warm" />

          <div className="ml-auto flex items-center gap-3">
            <UiLanguageToggle className="border-navy-600" />
            <DisplayLanguageToggle />
            <span className="hidden text-sm text-navy-100 sm:inline">
              {userName}
            </span>
            <RoleBadge role={role} className="border-navy-600 bg-navy-800 text-white" />
            <Button
              variant="ghost"
              size="sm"
              onClick={onSignOut}
              className="text-navy-100 hover:bg-white/10"
            >
              <LogOut aria-hidden />
              {t("nav.signOut")}
            </Button>
          </div>
        </div>

        <nav aria-label={t(titleKey)} className="mx-auto max-w-7xl px-5">
          <ul className="flex gap-1 overflow-x-auto">
            {nav.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "-mb-px inline-block border-b-2 px-3 py-2.5 text-sm whitespace-nowrap transition-colors",
                      active
                        ? "border-burnt font-medium text-white"
                        : "border-transparent text-navy-300 hover:text-white",
                    )}
                  >
                    {t(item.labelKey)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>

      <main id="main" className="mx-auto max-w-7xl px-5 py-7">
        {children}
      </main>
    </div>
  );
}

/** A consistent page heading inside the shell. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-navy-900">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-sand-700">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
