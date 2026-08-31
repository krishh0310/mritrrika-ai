"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ClipboardCheck, Gavel, ScanLine, User } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { homeFor, ROLE_LABELS, type Role } from "@/lib/session";
import { Button, Card, Field, Input, cn } from "@mrittika/ui";

/**
 * "Who are you?" then "prove it".
 *
 * §58 asks for four polished cards. What they actually do is choose which demo
 * account to pre-fill and which explanation to show — a convenience for a
 * hackathon audience, not an authorization step. The comment on the form says
 * so, in the interface, because a judge should be able to see that the
 * separation is real.
 */

type RoleCard = {
  role: Role;
  blurb: string;
  icon: typeof User;
  demoEmail: string;
};

const ROLE_CARDS: RoleCard[] = [
  {
    role: "CITIZEN",
    blurb: "Search and manage authorized land information.",
    icon: User,
    demoEmail: "ram31@mrittika.demo",
  },
  {
    role: "DEO",
    blurb: "Digitize and process legacy records.",
    icon: ScanLine,
    demoEmail: "deo@mrittika.demo",
  },
  {
    role: "VERIFIER",
    blurb: "Review AI extraction and validate records.",
    icon: ClipboardCheck,
    demoEmail: "lekhpal@mrittika.demo",
  },
  {
    role: "TEHSILDAR",
    blurb: "Approve verified records and monitor administration.",
    icon: Gavel,
    demoEmail: "tehsildar@mrittika.demo",
  },
];

/** A second citizen, so the isolation guarantee can be demonstrated live. */
const SECOND_CITIZEN = "seema32@mrittika.demo";

export function LoginScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const { signIn, user, loading } = useAuth();

  const requested = params.get("role");
  const [selected, setSelected] = useState<Role | null>(
    ROLE_CARDS.some((c) => c.role === requested) ? (requested as Role) : null,
  );
  const [email, setEmail] = useState(
    ROLE_CARDS.find((c) => c.role === requested)?.demoEmail ?? "",
  );
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in: go where this user belongs rather than showing a form
  // they do not need.
  useEffect(() => {
    if (!loading && user) router.replace(homeFor(user.roles));
  }, [loading, user, router]);

  function choose(card: RoleCard) {
    setSelected(card.role);
    setEmail(card.demoEmail);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await signIn(email.trim(), password);
      router.replace(homeFor(me.roles));
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Sign-in failed. Try again.",
      );
      setBusy(false);
    }
  }

  return (
    <main id="main" className="min-h-dvh bg-offwhite">
      <div className="mx-auto max-w-5xl px-6 py-10 md:py-16">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-navy-700 underline-offset-4 hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Mrittika AI
        </Link>

        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-navy-900">
          Who are you?
        </h1>
        <p className="mt-2 max-w-2xl text-[0.9375rem] text-sand-700">
          Pick the role you are here to use. This choice sets up the demo account
          and nothing else — your actual permissions come from your account on the
          server, checked on every request.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {ROLE_CARDS.map((card) => {
            const Icon = card.icon;
            const active = selected === card.role;
            return (
              <button
                key={card.role}
                type="button"
                onClick={() => choose(card)}
                aria-pressed={active}
                className={cn(
                  "flex flex-col items-start gap-2 rounded-card border bg-white p-4 text-left",
                  "shadow-panel transition-colors",
                  active
                    ? "border-burnt ring-1 ring-burnt"
                    : "border-sand-200 hover:border-navy-300",
                )}
              >
                <Icon
                  className={cn("size-5", active ? "text-burnt" : "text-navy-600")}
                  aria-hidden
                />
                <span className="text-sm font-semibold text-navy-900">
                  {ROLE_LABELS[card.role]}
                </span>
                <span className="text-xs leading-relaxed text-sand-500">
                  {card.blurb}
                </span>
              </button>
            );
          })}
        </div>

        <Card className="mt-8 max-w-lg">
          <form onSubmit={submit} className="p-5">
            <h2 className="text-sm font-semibold text-navy-900">
              {selected ? `Sign in as ${ROLE_LABELS[selected]}` : "Sign in"}
            </h2>

            <div className="mt-4 space-y-4">
              <Field label="Email" required>
                <Input
                  type="email"
                  name="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@mrittika.demo"
                />
              </Field>

              <Field
                label="Password"
                required
                hint="Demo accounts share one password, set by the seed script."
              >
                <Input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>
            </div>

            {error ? (
              <p
                role="alert"
                className="mt-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low"
              >
                {error}
              </p>
            ) : null}

            <Button type="submit" busy={busy} className="mt-5 w-full" size="lg">
              Sign in
            </Button>
          </form>

          {selected === "CITIZEN" ? (
            <div className="border-t border-sand-200 bg-sand-50 px-5 py-4">
              <p className="eyebrow">Two citizens, two dashboards</p>
              <p className="mt-1.5 text-xs leading-relaxed text-sand-700">
                Sign in as{" "}
                <button
                  type="button"
                  className="id underline underline-offset-2"
                  onClick={() => setEmail("ram31@mrittika.demo")}
                >
                  ram31@mrittika.demo
                </button>{" "}
                or{" "}
                <button
                  type="button"
                  className="id underline underline-offset-2"
                  onClick={() => setEmail(SECOND_CITIZEN)}
                >
                  {SECOND_CITIZEN}
                </button>{" "}
                to see that each holder gets only their own parcels.
              </p>
            </div>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
