# The existing system: how land records are digitized today

A study of the manual process Mrittika AI is designed to shorten, and of what
it can and cannot claim to improve. Figures marked † are listed at the end with
their stated sources, to be confirmed before external submission.

## 1. The current process

A citizen whose land has changed hands — by sale, inheritance or partition —
visits the tehsil office and submits a paper mutation application (Form 4 in
several states†). A Data Entry Operator transcribes the application and the
supporting legacy record into the state Land Records Management System (LRMS)
by hand. The Patwari (Lekhpal) conducts a field verification against the
physical khasra register. The Tehsildar reviews the file and signs it, and the
record is then updated in the LRMS, again manually.

Each hand-off is on paper or by re-keying, and the citizen has no view of
where the file is. The average end-to-end time is **21 working days**† (DoLR
baseline, 2022).

## 2. Pain points

- **Transcription errors of 8–12% for handwritten records**† (NIC / DILRMP
  digitization pilot observations, 2021). A mis-keyed khasra or share is
  carried into the digital record with nothing to flag it.
- **21 days on average per mutation**† (DoLR land management report, 2022).
- **3–5 citizen visits per mutation**†, to submit, follow up and collect.
- **About 15–20% of legacy LRMS records have missing or inconsistent data**†
  (CAG Report No. 13 of 2022, land records audit observations).
- **No tamper-evident audit trail** on paper records: a changed entry cannot
  be shown to have been changed, or by whom.
- **No duplicate detection.** After partition mutations the same parcel can
  appear under more than one khasra entry, and nothing checks for it.

## 3. Stakeholder burden

| Stakeholder | Current time / effort | Main pain | Mrittika addresses |
|---|---|---|---|
| Citizen | 3–5 visits, 21 days wait† | No status visibility | Mobile tracking and notifications; one visit, or none with self-upload from the app |
| DEO | Manual transcription, ~45 min per record† | Repetitive errors | Automatic extraction with per-field confidence flags |
| Patwari / Verifier | Paper cross-check with the khasra | No digital cross-reference | Automatic cross-check against the cadastre and PostGIS geometry |
| Tehsildar | Manual signature, no audit trail | Fraud risk | SHA-256 hash-chained audit of every state change, role-based access |
| State Revenue Dept | Aggregated manually from districts | No real-time view | Live state, district, tehsil and village dashboard |

## 4. What Mrittika improves (conservative claims)

- **Digitization time: 21 days → an estimated 3–5 days.** A person still
  reviews every record; the saving is in transcription and hand-offs, not in
  removing human judgement. This is an estimate, not a measurement.
- **Transcription errors are flagged before review, not after.** Every
  extracted field carries a confidence score; low-confidence fields are held
  for a verifier. On the synthetic corpus, 87.8% of AI-extracted fields were
  kept unchanged by verifiers.
- **Citizen visits: 3–5 → 1**, or none when a record is uploaded through the
  mobile app.
- **Audit trail:** a SHA-256 hash chain over every state change, and a
  QR-verifiable record certificate.
- **Duplicate detection** in two tiers: an exact file hash, then a perceptual
  (dHash) match that catches a rescan of a page already stored.

## 5. Limits of these claims

The prototype is measured on synthetic data: 500 generated Hindi land-record
pages degraded to four levels of scan quality, not real records. Its accuracy
figures (field-level F1 0.592 overall, 0.872 on clean scans) describe that
corpus. Handwritten records, the hardest case in the process above, are
flagged and routed to a human rather than read. Every accuracy and
time-saving claim here will be validated against real records in partnership
with a state revenue department before it is relied on.

---

### † Sources to confirm before submission

These figures and citations were supplied for this study and have not been
independently verified here. Check each against the original document:

1. 21 working days end-to-end — "DoLR baseline, 2022" / "DoLR land management report, 2022"
2. 8–12% transcription error rate for handwritten records — "NIC/DILRMP digitization pilot observations, 2021"
3. ~15–20% of legacy LRMS records with missing or inconsistent data — "CAG Report No. 13 of 2022"
4. 3–5 citizen visits per mutation, and ~45 minutes of DEO transcription per record — no source given
5. "Form 4" as the mutation application — the form number varies by state
