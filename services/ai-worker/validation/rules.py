"""Deterministic validation rules (§33).

Rules run BEFORE any ML (§7): they are explainable, cheap and produce findings
an officer can act on. A rule never blocks a document by itself -- it attaches
a finding, which feeds the confidence engine and the verifier's queue.

Wording matters (§34): findings describe an inconsistency, never an accusation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MAX_PLAUSIBLE_BIGHA = 200.0
MIN_PLAUSIBLE_BIGHA = 0.01

#: Proportional area change above which a jump is worth a human look.
AREA_JUMP_RATIO = 3.0


@dataclass
class Finding:
    rule: str
    severity: str          # info | warning | error
    message: str
    field: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


REQUIRED_FIELDS = ("VILLAGE", "KHASRA")


def check_required(values: dict[str, str | None]) -> list[Finding]:
    findings = []
    for field in REQUIRED_FIELDS:
        if not values.get(field):
            findings.append(
                Finding(
                    rule="REQUIRED_FIELD_MISSING",
                    severity="error",
                    message=f"{field} could not be read from this document.",
                    field=field,
                )
            )
    return findings


def check_khasra_format(values: dict[str, str | None]) -> list[Finding]:
    khasra = values.get("KHASRA")
    if not khasra:
        return []
    if not re.fullmatch(r"\d{1,5}(/\d{1,3})*", khasra):
        return [
            Finding(
                rule="MALFORMED_KHASRA",
                severity="warning",
                message=f"Khasra number '{khasra}' does not match the expected "
                        f"pattern (digits, optionally sub-divided with '/').",
                field="KHASRA",
            )
        ]
    return []


def check_khata_format(values: dict[str, str | None]) -> list[Finding]:
    khata = values.get("KHATA")
    if khata and not re.fullmatch(r"\d{1,6}", khata):
        return [
            Finding(
                rule="MALFORMED_KHATA",
                severity="warning",
                message=f"Khata number '{khata}' is not a plain number.",
                field="KHATA",
            )
        ]
    return []


def check_area_plausible(values: dict[str, str | None]) -> list[Finding]:
    raw = values.get("AREA")
    if not raw:
        return []
    try:
        area = float(raw)
    except ValueError:
        return [
            Finding(
                rule="MALFORMED_AREA", severity="warning",
                message=f"Area '{raw}' is not a number.", field="AREA",
            )
        ]
    unit = values.get("AREA_UNIT") or "BIGHA"
    if unit == "BIGHA" and not (MIN_PLAUSIBLE_BIGHA <= area <= MAX_PLAUSIBLE_BIGHA):
        return [
            Finding(
                rule="IMPLAUSIBLE_AREA", severity="warning",
                message=f"Recorded area {area} {unit.lower()} is outside the "
                        f"plausible range for a single plot.",
                field="AREA",
            )
        ]
    return []


def check_dates(values: dict[str, str | None]) -> list[Finding]:
    findings = []
    iso = values.get("DATE")
    if iso:
        try:
            parsed = date.fromisoformat(iso)
        except ValueError:
            findings.append(
                Finding("INVALID_DATE", "warning",
                        f"Date '{iso}' could not be interpreted.", "DATE")
            )
        else:
            if parsed > date.today():
                findings.append(
                    Finding("FUTURE_DATE", "warning",
                            f"Recorded date {iso} is in the future.", "DATE")
                )
            if parsed.year < 1900:
                findings.append(
                    Finding("IMPLAUSIBLE_DATE", "info",
                            f"Recorded date {iso} predates modern land records.",
                            "DATE")
                )
    return findings


def check_shares(shares: list[str]) -> list[Finding]:
    """Ownership shares on one record should total a whole (§39)."""
    if not shares:
        return []
    from fractions import Fraction

    total = Fraction(0)
    for share in shares:
        try:
            total += Fraction(share)
        except (ValueError, ZeroDivisionError):
            return [
                Finding("MALFORMED_SHARE", "warning",
                        f"Ownership share '{share}' is not a valid fraction.",
                        "SHARE")
            ]
    if total != 1:
        return [
            Finding(
                "SHARES_DO_NOT_TOTAL_ONE", "warning",
                f"Ownership shares on this document total {total}, not 1. "
                f"This may indicate a missing co-owner or a misread fraction.",
                "SHARE",
            )
        ]
    return []


def check_against_declared(
    values: dict[str, str | None], declared_khasra: str | None
) -> list[Finding]:
    """Cross-check the AI reading against what the operator typed at upload.

    A disagreement is not necessarily an error -- the operator may have mistyped
    -- so it is a warning that routes to human review, never an auto-correction.
    """
    extracted = values.get("KHASRA")
    if declared_khasra and extracted and declared_khasra != extracted:
        return [
            Finding(
                "DECLARED_KHASRA_MISMATCH", "warning",
                f"The khasra read from the document ('{extracted}') differs from "
                f"the one entered at upload ('{declared_khasra}').",
                "KHASRA",
            )
        ]
    return []


def check_area_change(
    values: dict[str, str | None], previous_area: float | None
) -> list[Finding]:
    """Large area change without a linked mutation (§33 worked example)."""
    raw = values.get("AREA")
    if not raw or previous_area is None or previous_area <= 0:
        return []
    try:
        area = float(raw)
    except ValueError:
        return []
    ratio = max(area, previous_area) / min(area, previous_area)
    if ratio >= AREA_JUMP_RATIO and not values.get("MUTATION"):
        return [
            Finding(
                "AREA_CHANGE_THRESHOLD", "warning",
                f"Area changed from {previous_area} to {area} without a linked "
                f"mutation on this document. Manual investigation recommended.",
                "AREA",
            )
        ]
    return []


def run_all(
    values: dict[str, str | None],
    *,
    shares: list[str] | None = None,
    declared_khasra: str | None = None,
    previous_area: float | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_required(values)
    findings += check_khasra_format(values)
    findings += check_khata_format(values)
    findings += check_area_plausible(values)
    findings += check_dates(values)
    findings += check_shares(shares or [])
    findings += check_against_declared(values, declared_khasra)
    findings += check_area_change(values, previous_area)
    return findings


def validation_confidence(findings: list[Finding], field: str) -> float:
    """Turn rule outcomes into a per-field confidence signal (§8).

    An error on a field is strong evidence the value is wrong; a warning is
    weaker. Clean fields get a mild positive signal rather than 1.0, because
    'no rule fired' is not proof of correctness.
    """
    relevant = [f for f in findings if f.field == field]
    if any(f.severity == "error" for f in relevant):
        return 0.05
    if any(f.severity == "warning" for f in relevant):
        return 0.45
    if any(f.severity == "info" for f in relevant):
        return 0.75
    return 0.85
