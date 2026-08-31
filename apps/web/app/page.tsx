import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { LifecycleChain } from "@/components/marketing/lifecycle-chain";
import { Button, SyntheticNotice } from "@mrittika/ui";

/**
 * The landing page (§57).
 *
 * The hero is the record lifecycle itself rather than a headline over a
 * gradient. The lifecycle IS the product — §92 says a working end-to-end
 * vertical slice matters more than any feature list — so showing the chain,
 * with the role that owns each link, states the thesis in the space where a
 * marketing page would otherwise put a stock illustration.
 */
export default function LandingPage() {
  return (
    <main id="main" className="min-h-dvh bg-offwhite">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-navy-900 text-white">
        {/* A faint cadastral grid: the subject's own material, at 4% so it
            reads as paper texture rather than decoration. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
            backgroundSize: "72px 72px",
          }}
        />

        <div className="relative mx-auto max-w-6xl px-6 py-16 md:py-24">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold tracking-tight">Mrittika AI</span>
            <SyntheticNotice />
          </div>

          <h1 className="mt-10 max-w-3xl text-4xl leading-[1.1] font-semibold tracking-tight md:text-6xl">
            Intelligent digitization for India&rsquo;s land records
          </h1>

          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-navy-100">
            Transforming fragmented, multilingual and historical land records into
            structured, searchable and verifiable digital intelligence.
          </p>

          <div className="mt-9 flex flex-wrap gap-3">
            <Button asChild variant="accent" size="lg">
              <Link href="/login?role=officer">
                Officer login
                <ArrowRight aria-hidden />
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              className="bg-white text-navy-900 hover:bg-cream"
            >
              <Link href="/login?role=CITIZEN">Citizen access</Link>
            </Button>
            <Button
              asChild
              variant="ghost"
              size="lg"
              className="text-white hover:bg-white/10"
            >
              <Link href="#lifecycle">Explore the platform</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* ── The lifecycle: this page's signature ─────────────────────────── */}
      <section id="lifecycle" className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <p className="eyebrow">How a record is made</p>
        <h2 className="mt-2 max-w-2xl text-2xl font-semibold tracking-tight text-navy-900 md:text-3xl">
          One document. Four hands. Every step recorded.
        </h2>
        <p className="mt-3 max-w-2xl text-[0.9375rem] leading-relaxed text-sand-700">
          A scan enters at the left and leaves as an approved record of rights. The
          same <span className="id">document_id</span>,{" "}
          <span className="id">record_id</span> and{" "}
          <span className="id">parcel_id</span> travel the whole way, so the audit
          trail at the end describes the work that actually happened.
        </p>

        <LifecycleChain className="mt-10" />
      </section>

      {/* ── What the system will and will not claim (§69) ─────────────────── */}
      <section className="border-t border-sand-200 bg-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 md:grid-cols-2">
          <div>
            <p className="eyebrow">What this prototype does</p>
            <ul className="mt-4 space-y-3 text-[0.9375rem] leading-relaxed text-sand-700">
              {[
                "Reads degraded Hindi and English land documents, keeping the raw OCR beside every normalized value.",
                "Scores each field's confidence separately, so a reviewer knows which line to check first.",
                "Puts a human in the loop before anything becomes a record, and a second human before it is approved.",
                "Links every record to a cadastral parcel, its owners, and its mutation history.",
                "Answers questions from the database, with citations — never from the model's memory.",
                "Hash-chains every sensitive action into an audit trail you can verify.",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <span
                    aria-hidden
                    className="mt-2 size-1.5 shrink-0 rounded-full bg-burnt"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="eyebrow">What it does not</p>
            <p className="mt-4 text-[0.9375rem] leading-relaxed text-sand-700">
              This is a hackathon prototype running entirely on synthetic records. It
              is not connected to any government system, holds no real citizen&rsquo;s
              land, and makes no accuracy claim it has not measured.
            </p>
            <p className="mt-4 text-[0.9375rem] leading-relaxed text-sand-700">
              Where the architecture is ready for something it has not implemented —
              a DILRMP connector, handwriting recognition, federated training — it is
              labelled a future extension rather than described as working.
            </p>
            <p className="mt-6 rounded-card border border-dashed border-burnt bg-cream px-4 py-3 text-sm text-sand-700">
              Every record, owner, parcel and document in this deployment was
              generated. Any resemblance to a real holding is coincidental.
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-sand-200 bg-offwhite">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-sand-500">
          <p>Mrittika AI — prototype build, synthetic data only.</p>
          <Link href="/login" className="text-navy-700 underline-offset-4 hover:underline">
            Sign in
          </Link>
        </div>
      </footer>
    </main>
  );
}
