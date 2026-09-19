# Running the demo

The §70 walkthrough, on real application state. The same `document_id` and
`parcel_id` travel every step — none of it is staged.

## Start the stack

```bash
docker compose up -d                 # postgres + postgis, redis, minio
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
.venv/bin/python scripts/seed_demo.py

# API (native, not in Docker — see docs/architecture.md "Runtime topology")
.venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000

# Web
npm run dev
```

Check `http://localhost:8000/ready` before continuing. It should report
`postgis: ok` and `pgvector: ok` — a database missing either fails later in a
confusing way.

## Accounts

All share one password from the seed configuration (`demo_change_me` by
default).

| role | email |
|---|---|
| Citizen | `ram31@mrittika.demo` |
| Citizen (a second one) | `seema32@mrittika.demo` |
| Data Entry Operator | `deo@mrittika.demo` |
| Verifier / Lekhpal | `lekhpal@mrittika.demo` |
| Tehsildar | `tehsildar@mrittika.demo` |

Two citizens exist so the isolation guarantee can be demonstrated live rather
than described.

## The walkthrough

**A degraded Hindi Khasra page, end to end. Around six minutes.**

### 1 — Capture (DEO)

Sign in as the DEO. **Upload** → drop
`datasets/generated/degraded/DOC-00021.jpg`.

Set type `KHASRA`, village `रामपुर`, record year `1998-99`, and parcel
`PARCEL-UP-DEMO-0144`.

> The parcel link is what makes step 5 possible. Without it the document is
> still processed, but it has no history to be checked against.

### 2 — The quality gate

The upload lands on the document page with the §22 report already computed —
sharpness, contrast, resolution, straightness, brightness, and a verdict.

This degraded scan scores around **0.51, "processable with warnings"**. Worth
pausing on: the gate ran *before* any model, and a page scoring below the
rejection threshold would have been sent back for a rescan rather than guessed
at.

### 3 — Processing

**Start processing.** The stage list advances through quality → enhancement →
text recognition → layout → field extraction → normalization → validation →
confidence.

This is real PaddleOCR on a real degraded page. It takes 10–40 seconds
depending on whether the model is warm.

### 4 — Verification (Verifier)

Sign in as the lekhpal. The document is **already in the queue** — nobody put
it there by hand.

Open it. This is the §28 workspace, and the thing to show:

* Fields are ordered **least certain first**.
* The **Area** field reads `RAW २७६ → NORMALIZED 276`. The OCR read a
  mixed-script numeral off a blurred page, and *both* values survived — §26
  forbids normalization destroying the raw value.
* A validation finding sits under it: **`IMPLAUSIBLE_AREA`** — 276 bigha is not
  a single plot.
* **Click the field.** The scan scrolls and zooms to the region it was read
  from. **Click a box on the scan.** The field focuses. One shared selection,
  both directions.
* Boxes are coloured by confidence. Toggle **Confidence** off and on.

Correct the area to `2.76` and submit.

> The correction does not overwrite the prediction. The next screen proves it.

### 5 — Approval (Tehsildar)

Sign in as the tehsildar. Open the document from **Approvals**.

* **Verifier corrections** shows `276` struck through, `2.76` beside it, and
  who changed it.
* **Potential inconsistencies** shows the anomaly the engine raised when the
  document was processed: an `AREA_JUMP`, because 276 against a parcel of
  record 0.29 hectare is a 951× change. It carries its evidence and it says
  *manual investigation recommended* — never "fraud".
* Ownership history, mutations and the audit timeline are on the same screen,
  because "should this become the record of rights?" is a different question
  from "is this transcribed correctly?".

**Approve.**

### 6 — The citizen (Citizen A)

Sign in as `ram31@mrittika.demo`.

* The dashboard greets राम प्रसाद सिंह and lists five parcels — including
  `PARCEL-UP-DEMO-0144`, the one just approved.
* **Map** — the Voronoi cadastre of रामपुर, with this citizen's parcels filled
  in orange and the rest of the village drawn as context. Click one; the side
  panel shows the record and its ownership history.
* **Record** → the ownership timeline, grouped by the date holdings changed,
  with the mutation that caused each change.

### 7 — The assistant

**Ask AI** → *"Who was the recorded owner of this parcel in 1998?"*

The answer comes back with **citations**: the parcel and ownership records it
was built from. Not from the model's memory — §9 makes the database the source
of truth and the model only explains it.

If no LLM is reachable the screen says so and shows the structured result
alone (§82), rather than passing a database lookup off as a generated answer.

### 8 — The audit trail

Open `/audit/DOC-000NN` (the id from step 1).

Upload → quality → processing → correction → verification → approval, in
order, each hashed together with the one before it. Expand any event to see
before/after state.

**Verify the chain.** It recomputes every hash and reports how many events it
checked. Altering one past event would break every hash after it.

> Say "hash chain", not "blockchain". §41 is explicit, and so is the UI.

### 9 — Isolation

Sign out. Sign in as `seema32@mrittika.demo`.

A different dashboard, different parcels. Then paste Citizen A's parcel into
the URL: `/citizen/records/PARCEL-UP-DEMO-0144`.

**"This parcel is not recorded against your name."** The refusal is identical
to the one for a parcel that does not exist — a citizen must not be able to
learn which ids are real by comparing responses.

## Running it as a test instead

The whole walkthrough is automated:

```bash
npx playwright test --config apps/web/playwright.config.ts
```

11 tests: the seven lifecycle steps above, plus the four §72 isolation checks.
It drives the real stack, so it needs the servers up.

## If something goes wrong

| symptom | cause |
|---|---|
| `/ready` says `database: error` | Postgres is not up — `docker compose up -d` |
| `postgis: missing` | the container built without the extension; rebuild `infrastructure/docker/postgres` |
| Processing returns 503 | no Celery worker. The UI uses `synchronous=true`, which runs the **same** pipeline inline — it is not a mock path |
| The scan does not render in the workspace | MinIO is down; presigned URLs fail. Field boxes still position correctly |
| The verifier queue is empty | every seeded document has already been approved. Upload a new one — that is step 1 |
| The assistant answers without citations | no records matched. It says so rather than inventing any |

## What not to claim while demonstrating

§69, worth having in front of you:

- Not connected to DILRMP, BhuNaksha, or any government system.
- Handwritten lines are detected and read by models trained on public handwriting datasets, not land records, and every field on the page requires review. The queue's Handwriting column shows which reader read them and, if enabled, whether Gemini agreed. See [docs/handwriting.md](handwriting.md).
- No layout or language model in extraction. PP-Structure, LayoutLMv3 and
  IndicBERT are not integrated; extraction is deterministic rules.
- No blockchain. A SHA-256 hash chain.
- No accuracy figure that has not been measured; `scripts/evaluate_extraction.py`
  reports per difficulty tier and that is the only number to quote.
- Every record is synthetic. The prototype holds no real citizen's land.
