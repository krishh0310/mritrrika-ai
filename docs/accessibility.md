# Accessibility review

The web app uses semantic `main`, `header`, navigation, labels, buttons, tables, and form controls. The shared field component associates labels and inputs; icon-only controls must have an accessible name. The app shell exposes a main landmark and visible keyboard focus. The UI also respects `prefers-reduced-motion`.

## Contrast corrections (2026-09-30)

The former small-text tokens failed WCAG AA on their usual surfaces: sand text on white was 3.79:1, medium status text on its pale chip was 2.81:1, and burnt text on white was 3.63:1. The updated tokens measure **6.00:1** (`#6b6254` on white), **5.93:1** (`#805309` on `#fbf1dd`), and **6.49:1** (`#9a4512` on white). A warm focus outline is used in the dark header, where the darker burnt color would not meet the 3:1 focus contrast threshold.

The values above are calculated using the WCAG relative luminance formula for the specified foreground/background pairs. They do not establish whole-page WCAG conformance. Run keyboard and screen-reader checks on each flow before a public deployment; automated contrast checks cannot verify reading order, dynamic announcements, or map alternatives.

## Forensic panel checks

`apps/web/components/verifier/forensics-panel.test.tsx` verifies keyboard consent and activation, completion announcements, Hindi labels and verdicts, and an announced retrieval failure with retry. Consent explicitly discloses Google Gemini processing before this UI sends a scan. Results are labeled unvalidated AI advice requiring human review; provider prose remains in the returned language with that limitation disclosed. English/Hindi message keys pass parity checks (192 keys).

These component tests do not establish whole-workflow WCAG conformance. Full browser audits, screen-reader review, zoom, responsive Indic rendering and map alternatives remain to be verified.
