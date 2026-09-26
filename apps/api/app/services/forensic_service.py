# ruff: noqa: E501 -- the prompts are kept verbatim, one instruction per line.
"""Gemini forensic checks: tamper, stamp, signature, area, cross-document fraud.

Prototype-grade and advisory. Every check is one prompt to the configured
Gemini model asking for a JSON object; nothing is trained or run locally. A
result is a lead for the verifier, never a finding against a person (§34), and
never changes a document's state.

Run on demand from the verification workspace, not in the pipeline: each run
sends the scan to Google, which the rest of this codebase keeps opt-in (see
gemini_handwriting_enabled).

Any failure -- no key, network, unparsable reply -- stores UNABLE_TO_VERIFY
with the error, so a missing check is visible rather than silently green.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time

import httpx
from geoalchemy2 import Geography
from mrittika_domain.area import (
    SQM_PER_HECTARE,
    UnknownAreaUnit,
    relative_difference,
    to_square_metres,
)
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import (
    Document,
    DocumentPage,
    ForensicReport,
    Location,
    Mutation,
    Owner,
    OwnershipRecord,
    Parcel,
)
from app.services import document_service, storage_service
from app.services.cross_reference_service import _values, check_parcel_exists

logger = logging.getLogger(__name__)

UNABLE = "UNABLE_TO_VERIFY"
CHECKS = ("tamper", "stamp", "signature", "area", "fraud")

#: Which result key is each check's headline verdict / numeric score.
VERDICT_KEYS = {
    "tamper": ("authenticity_verdict", "tamper_score"),
    "stamp": ("overall_assessment", None),
    "signature": ("overall_verdict", None),
    "area": ("tolerance_assessment", "difference_percent"),
    "fraud": ("risk_level", "risk_score"),
}

# ── prompts ──────────────────────────────────────────────────────────────

TAMPER_PROMPT = """Analyze this scanned land record document for signs of digital tampering or forgery.
Check for:
1. Inconsistent JPEG compression artifacts
2. Copy-paste regions (duplicated stamps, text, signatures)
3. Mismatched fonts or font sizes within same document
4. Misaligned text or tables
5. Unnatural color gradients or noise patterns
6. Missing or inconsistent metadata signatures

Return ONLY a JSON object:
{
  "tamper_score": 0-100,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "findings": [
    {"issue": "description", "severity": "CRITICAL" | "WARNING" | "INFO", "location": "general or specific region"}
  ],
  "authenticity_verdict": "AUTHENTIC" | "SUSPICIOUS" | "FORGED",
  "explanation": "brief reasoning in English and Hindi"
}"""

STAMP_PROMPT = """Examine this land record document for official stamps, seals, or government markings.
Identify:
1. Number of stamps present
2. Stamp type (circular rubber, rectangular seal, embossed, wet signature, none)
3. Visible text on stamp (department, officer name, date if readable)
4. Stamp quality (clear, faded, partial, missing)
5. Any signs the stamp was copied from another document
6. Whether multiple stamps appear to be from different time periods

Return ONLY a JSON object:
{
  "stamp_count": number,
  "stamps": [
    {
      "type": "circular_rubber" | "rectangular_seal" | "embossed" | "wet_signature" | "unknown",
      "quality": "CLEAR" | "FADED" | "PARTIAL" | "MISSING",
      "readable_text": "extracted text or null",
      "suspicious": true | false,
      "suspicion_reason": "reason if suspicious"
    }
  ],
  "overall_assessment": "AUTHENTIC" | "REVIEW" | "SUSPICIOUS",
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}"""

SIGNATURE_PROMPT = """Analyze the signature(s) in this land record document.
The document claims to be signed by: {owner_name}

Evaluate:
1. How many signatures are present
2. Signature consistency (does it look like one person's handwriting or multiple)
3. Pressure patterns (natural variation vs uniform/printed)
4. Whether signature appears traced, photocopied, or digitally inserted
5. Comparison to typical government document signatures from rural India
6. Any mismatch between claimed owner name and signature style

Return ONLY a JSON object:
{{
  "signature_count": number,
  "signatures": [
    {{
      "location": "general area description",
      "quality": "CLEAR" | "FADED" | "PARTIAL",
      "naturalness_score": 0-100,
      "suspicious_indicators": ["list of concerns"],
      "verdict": "AUTHENTIC" | "REVIEW" | "FORGED"
    }}
  ],
  "name_match_assessment": "MATCHES" | "UNCLEAR" | "MISMATCH",
  "overall_verdict": "AUTHENTIC" | "REVIEW" | "FORGED",
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}}"""

AREA_PROMPT = """A land record claims an area of {claimed_area} {unit} ({converted_ha} hectares).
The GIS polygon for this parcel measures {gis_area_ha} hectares.
The percentage difference is {diff_percent}%.

Context: This is a {state} land record from {year}. Local survey practices may have ±5% variance.

Assess:
1. Is this difference within normal survey tolerance?
2. Could this indicate data entry error, fraud, or boundary dispute?
3. Historical context: were old surveys less accurate?

Return ONLY a JSON object:
{{
  "claimed_area_ha": number,
  "gis_area_ha": number,
  "difference_percent": number,
  "tolerance_assessment": "WITHIN_TOLERANCE" | "MINOR_DEVIATION" | "SIGNIFICANT_MISMATCH" | "CRITICAL_MISMATCH",
  "likely_cause": "SURVEY_VARIANCE" | "DATA_ENTRY_ERROR" | "BOUNDARY_CHANGE" | "FRAUD_SUSPECTED" | "UNKNOWN",
  "recommended_action": "NONE" | "NOTE" | "VERIFY" | "ESCALATE",
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}}"""

FRAUD_PROMPT = """Analyze this land parcel's transaction history for fraud patterns.
Parcel: {parcel_id}
Current Owner: {current_owner}
Area: {area}
Document under review: {document_type}, extracted fields: {fields}
Transaction History:
{formatted_history}
Connected Persons:
{connected_persons}
Check for:
Circular ownership (A→B→C→A)
Rapid flipping (>3 transactions in 12 months)
Area inflation without survey
Impossible dates (mutation before sale deed)
Common witnesses across unrelated transactions
Nominee patterns (family members holding multiple parcels)
Unusual price patterns (if available)
Return ONLY a JSON object:
{{
"risk_score": 0-100,
"risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
"patterns_detected": [
{{"pattern": "name", "description": "details", "severity": "LOW" | "MEDIUM" | "HIGH"}}
],
"suspicious_entities": ["list of persons/parcels to investigate"],
"recommended_action": "NONE" | "MONITOR" | "REVIEW" | "INVESTIGATE",
"confidence": "HIGH" | "MEDIUM" | "LOW"
}}"""

# ── Gemini ───────────────────────────────────────────────────────────────

#: Free-tier rate limits: at most one call per second, across all requests in
#: this process. ponytail: per-process throttle; a shared limiter (Redis) if
#: several API workers start tripping 429s.
MIN_INTERVAL_SECONDS = 1.0
_throttle = threading.Lock()
_last_call = 0.0


class Unverifiable(Exception):
    """The check could not run; the message is shown to the verifier."""


def parse_json(text: str) -> dict:
    """The first {...} in a model reply, tolerating ```json fences and prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise Unverifiable("analysis returned no result")
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise Unverifiable(f"analysis returned an unreadable result: {exc}") from exc
    if not isinstance(parsed, dict):
        raise Unverifiable("analysis returned an unreadable result")
    return parsed


def ask_gemini(prompt: str, image: tuple[bytes, str] | None = None) -> dict:
    """One interactions-API call (same endpoint as rag_service), parsed."""
    global _last_call
    settings = get_settings()
    if not settings.gemini_api_key:
        raise Unverifiable("forensic analysis is not configured")

    parts: list[dict] = []
    if image is not None:
        data, mime = image
        parts.append({"type": "image", "mime_type": mime,
                      "data": base64.b64encode(data).decode("ascii")})
    parts.append({"type": "text", "text": prompt})

    with _throttle:
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            response = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": settings.gemini_api_key},
                json={"model": settings.gemini_llm_model, "input": parts},
                timeout=90,
            )
            if response.is_error:  # Google's message says why (bad key, quota...)
                logger.warning("forensic model call failed: %s", response.text[:500])
                raise Unverifiable(f"analysis service error {response.status_code}")
        except httpx.HTTPError as exc:
            raise Unverifiable(f"analysis service unreachable: {exc}") from exc
        finally:
            _last_call = time.monotonic()

    text = "\n".join(
        content["text"]
        for step in response.json().get("steps", [])
        if step.get("type") == "model_output"
        for content in step.get("content", [])
        if content.get("type") == "text" and content.get("text")
    )
    return parse_json(text)


# ── inputs ───────────────────────────────────────────────────────────────

def _page_image(session: Session, document: Document) -> tuple[bytes, str]:
    """First page as an image. A PDF upload is read from its rendered page."""
    page = session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number).limit(1)
    ).scalar_one_or_none()
    if page is not None and page.storage_key:
        data = storage_service.get_bytes(
            page.storage_key, bucket=document_service.page_bucket(document, page))
    else:
        data = storage_service.get_bytes(document.storage_key)
    mime = storage_service.sniff_mime(data)
    if mime not in ("image/png", "image/jpeg"):
        raise Unverifiable("no page image yet -- process the document first")
    return data, mime


def _parcel(session: Session, document: Document, values: dict) -> Parcel | None:
    if document.parcel_id:
        return session.get(Parcel, document.parcel_id)
    village = session.get(Location, document.village_id) if document.village_id else None
    return check_parcel_exists(session, values, village)[0]


def _state_name(session: Session, location_id: str | None) -> str:
    node = session.get(Location, location_id) if location_id else None
    for _ in range(8):
        if node is None:
            break
        if node.level.upper() == "STATE":
            return node.name
        node = session.get(Location, node.parent_id) if node.parent_id else None
    return "Indian"


# ── the five checks ──────────────────────────────────────────────────────

def check_tamper(session: Session, document: Document, values: dict) -> dict:
    return ask_gemini(TAMPER_PROMPT, _page_image(session, document))


def check_stamp(session: Session, document: Document, values: dict) -> dict:
    return ask_gemini(STAMP_PROMPT, _page_image(session, document))


def check_signature(session: Session, document: Document, values: dict) -> dict:
    owner = values.get("OWNER") or "(owner name not extracted)"
    return ask_gemini(SIGNATURE_PROMPT.format(owner_name=owner),
                      _page_image(session, document))


def check_area(session: Session, document: Document, values: dict) -> dict:
    parcel = _parcel(session, document, values)
    if parcel is None or parcel.geometry is None:
        raise Unverifiable("no parcel polygon to compare against")
    stated = values.get("AREA")
    if not stated:
        raise Unverifiable("no area was extracted from the page")
    try:
        claimed = float(str(stated).replace(",", ""))
    except ValueError:
        raise Unverifiable(f"extracted area {stated!r} is not a number") from None
    # A page with no unit is read in the cadastre's unit, as cross_reference does.
    unit = values.get("AREA_UNIT") or parcel.area_unit
    try:
        claimed_sqm = to_square_metres(claimed, unit)
    except UnknownAreaUnit as exc:
        raise Unverifiable(str(exc)) from None

    gis_sqm = session.execute(
        select(func.ST_Area(cast(Parcel.geometry, Geography))).where(Parcel.id == parcel.id)
    ).scalar()
    if not gis_sqm:
        raise Unverifiable("parcel polygon has no measurable area")

    diff = relative_difference(claimed_sqm, float(gis_sqm))
    return ask_gemini(AREA_PROMPT.format(
        claimed_area=claimed, unit=unit.lower(),
        converted_ha=round(claimed_sqm / SQM_PER_HECTARE, 4),
        gis_area_ha=round(float(gis_sqm) / SQM_PER_HECTARE, 4),
        diff_percent=round(diff * 100, 2),
        state=_state_name(session, parcel.village_id),
        year=document.record_year or "an unknown year",
    ))


def check_fraud(session: Session, document: Document, values: dict) -> dict:
    parcel = _parcel(session, document, values)
    if parcel is None:
        raise Unverifiable("document is not linked to a known parcel")

    holdings = session.execute(
        select(OwnershipRecord, Owner, Mutation)
        .join(Owner, Owner.id == OwnershipRecord.owner_id)
        .outerjoin(Mutation, Mutation.id == OwnershipRecord.mutation_id)
        .where(OwnershipRecord.parcel_id == parcel.id)
        .order_by(OwnershipRecord.valid_from)
    ).all()
    mutations = session.execute(
        select(Mutation).where(Mutation.parcel_id == parcel.id)
        .order_by(Mutation.effective_date)
    ).scalars().all()
    documents = session.execute(
        select(Document).where(Document.parcel_id == parcel.id)
        .order_by(Document.created_at)
    ).scalars().all()

    history = [
        f"- OWNERSHIP {o.name} share {r.share} from {r.valid_from} to "
        f"{r.valid_to or 'present'} ({r.status})"
        + (f" via mutation {m.mutation_number}" if m else "")
        for r, o, m in holdings
    ] + [
        f"- MUTATION {m.mutation_number} {m.mutation_type} effective {m.effective_date}"
        f" registered {m.registration_date or 'unknown'} ({m.status})"
        for m in mutations
    ] + [
        f"- DOCUMENT {d.external_id} {d.document_type} year {d.record_year or '?'} ({d.state})"
        for d in documents
    ]

    # Connected persons: everyone who has held this parcel, and what else they hold.
    owner_ids = {o.id for _, o, _ in holdings}
    other = session.execute(
        select(Owner.name, Parcel.external_id, Parcel.khasra_number)
        .join(OwnershipRecord, OwnershipRecord.owner_id == Owner.id)
        .join(Parcel, Parcel.id == OwnershipRecord.parcel_id)
        .where(Owner.id.in_(owner_ids), Parcel.id != parcel.id)
    ).all() if owner_ids else []
    elsewhere: dict[str, list[str]] = {}
    for name, ext_id, khasra in other:
        elsewhere.setdefault(name, []).append(f"{ext_id} (khasra {khasra})")
    persons = [
        f"- {o.name} (guardian: {o.guardian_name or 'unknown'}); other parcels: "
        f"{', '.join(elsewhere.get(o.name, [])) or 'none'}"
        for o in {o.id: o for _, o, _ in holdings}.values()
    ]

    current = [o.name for r, o, _ in holdings if r.valid_to is None]
    return ask_gemini(FRAUD_PROMPT.format(
        parcel_id=f"{parcel.external_id} (khasra {parcel.khasra_number})",
        current_owner=", ".join(current) or "none recorded",
        area=f"{parcel.area_value} {parcel.area_unit.lower()}",
        document_type=document.document_type,
        fields=json.dumps(values, ensure_ascii=False),
        formatted_history="\n".join(history) or "(no recorded transactions)",
        connected_persons="\n".join(persons) or "(none recorded)",
    ))


RUNNERS = {
    "tamper": check_tamper,
    "stamp": check_stamp,
    "signature": check_signature,
    "area": check_area,
    "fraud": check_fraud,
}


def run(session: Session, document: Document, checks: tuple[str, ...] = CHECKS
        ) -> list[ForensicReport]:
    """Run each check, store one report per check (failures included)."""
    values = _values(session, document)
    model = get_settings().gemini_llm_model
    reports = []
    for check in checks:
        verdict_key, score_key = VERDICT_KEYS[check]
        try:
            result = RUNNERS[check](session, document, values)
            verdict = str(result.get(verdict_key) or UNABLE).upper()
        except Exception as exc:  # any failure is a visible UNABLE_TO_VERIFY
            logger.warning("forensic %s check failed for %s: %s",
                           check, document.external_id, exc)
            result, verdict = {"error": str(exc)}, UNABLE
        score = result.get(score_key) if score_key else None
        report = ForensicReport(
            document_id=document.id, check=check, verdict=verdict[:32],
            score=float(score) if isinstance(score, (int, float)) else None,
            result=result, model_version=model,
        )
        session.add(report)
        reports.append(report)
    session.flush()
    return reports


def latest(session: Session, document: Document) -> list[ForensicReport]:
    """The newest report per check, in CHECKS order."""
    rows = session.execute(
        select(ForensicReport).where(ForensicReport.document_id == document.id)
        .order_by(ForensicReport.created_at.desc())
    ).scalars()
    newest: dict[str, ForensicReport] = {}
    for row in rows:
        newest.setdefault(row.check, row)
    return [newest[c] for c in CHECKS if c in newest]


def to_dict(report: ForensicReport) -> dict:
    return {
        "check": report.check,
        "verdict": report.verdict,
        "score": report.score,
        "result": report.result,
        "model_version": report.model_version,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
