# Close the audited gaps, and say honestly which ones were not real

> Ready to paste once a remote exists. `git remote -v` is empty in this
> workspace, so the branch could not be pushed and no PR could be opened from
> here. 13 commits on `fix/cadastre-extraction-rag-e2e`.

## What this is

A gap list written against a build report drove this work. The first thing done
was to check that list against the code. Three of its items were not real, one
of its items was already built, and something it never mentioned was silently
broken. `docs/gap-audit.md` records every verdict with evidence.

## What the audit found before any feature was written

| Claim | Reality |
|---|---|
| No Isolation Forest anomaly detection | **Already built and wired** — corpus fitting with a 30-record floor, suppressed when a rule already fired, degrading to rules when scikit-learn is absent. Not rebuilt. |
| Mobile app does not build | **It built then and builds now** — `tsc` clean, `expo export` bundles 420 modules. |
| Empty committed `infrastructure/monitoring` and `nginx` | **Neither was in git.** Untracked local directories referenced by nothing. |
| No Prometheus metrics | **`/metrics` already emitted nine metrics'** worth of Prometheus text format. Only the scrape and the dashboard were missing. |
| *(not in the list)* | **The layout ground truth was wrong on all 500 pages** — boxes written in pre-degradation coordinates while the annotation recorded the post-degradation size. Nothing read them, so nothing caught it. |

## What was built

**Vision.** YOLOv8 fine-tuned on the generator's own layout ground truth:
**mAP50-95 0.958**, exact ground-truth instance counts on all 75 val pages.
It **does not improve extraction** — F1 0.592 → 0.593 — because extraction is
bottlenecked by OCR recall (0.49) rather than by region confusion. So it is
opt-in and off by default. The control arm was re-measured first and reproduced
the baseline exactly, so the comparison is like-for-like.

**OCR.** Six scripts read (Devanagari, Telugu, Tamil, Kannada, Latin, Urdu) and
five identified-and-refused *by name*. Routing recognises with each candidate
and scores confidence × script agreement, because a Devanagari recogniser on a
Telugu page returns plausible-looking rubbish at 0.62. Proven end to end on
rendered pages.

**Validation.** Exact-duplicate refusal (409, naming the original) plus
near-duplicate flagging, because a rescan after a quality rejection produces
exactly that signal and must not be blocked. Cross-reference checks against the
location hierarchy, the cadastre and the PostGIS geometry — in their own
response key, so nobody edits the page to match the reference. `ai_feedback`
now has a writer that ranks a *confident* wrong answer above an unsure one.

**GIS.** GeoServer serving 160 approved parcels over WMS/WFS. Ownership is
unreachable at the database level, not merely omitted from a query:

```
$ psql -U geoserver_reader -c 'SELECT * FROM owners LIMIT 1;'
ERROR:  permission denied for table owners
```

**Notifications.** Template-based providers for WhatsApp Cloud API and MSG91,
because both regimes require registered templates and an unregistered SMS is
*accepted by the gateway and dropped by the operator*. No template carries
record content — they are read on lock screens.

**Bilingual UI.** Hindi and English chrome across web and mobile from one
shared catalogue. Key parity is a **type error**, not a lint rule. Record values
are never translated, and a browser test proves it by comparing the numbers in
a table across a language switch.

**Product.** A printable record extract with a verifying QR; DEO batch upload
where partial success is the normal case; Prometheus + Grafana with nine
operational panels.

## Three bugs found by tests rather than by review

1. **Layout ground truth** was geometrically wrong on every page (above).
2. **The language switcher was inaccessible.** With the interface in Hindi, the
   "switch to English" control was announced as *"इंटरफ़ेस अंग्रेज़ी में बदलें"* —
   unreachable to a screen-reader user who cannot read Hindi, which is exactly
   the person it exists for. Both the label and the accessible name now come
   from the language each option switches *to*.
3. **The e2e suite was flaky by construction.** It uploaded corpus files
   verbatim, so once duplicate detection landed it passed on the first run and
   failed on every run after. A shared `freshScan` helper fixes it.

## What was deliberately not done

* **LayoutLMv3 / IndicBERT fine-tuning** — skipped on the maintainer's
  instruction, with the Phase 2 measurement as the reason: it sits downstream of
  the same OCR that bounds extraction, so it would most likely reproduce the
  same null result at several times the cost.
* **Officer screen body copy is not translated.** Their chrome and navigation
  are; the verifier workspace and tehsildar analytics copy stay English, which
  is their default. Listed in `docs/i18n.md`.
* The certificate PDF **has no text layer** — the cost of shaping Devanagari
  correctly with Pillow rather than mis-shaping it with reportlab. A test fails
  loudly if that ever changes.

Every "what is NOT done" list in the new docs is there for the same reason: so
nothing above reads as a claim.

## Verification

| check | result |
|---|---|
| `ruff check .` | clean |
| `pytest tests` | 580 passed, 1 skipped (baseline 387) |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm test` | 38 passed |
| `npm run build` / `build:mobile` | both succeed |
| Playwright | 25 passed (baseline 17) |
| `scripts/check_i18n.py` | 137 keys, en + hi in parity |

New docs: `gap-audit.md`, `gis-integration.md`, `deployment.md`, `i18n.md`,
`monitoring.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
