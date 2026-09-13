"""Check a document against the records it claims to describe (§33, §34).

validation/rules.py answers "is this value well-formed?" -- a date that parses,
an area inside plausible bounds, a khasra number shaped like a khasra number. A
page can pass every one of those and still be about a parcel that does not
exist, in a village it does not belong to, claiming three times the land the
cadastre records.

This module answers the other question: does what the document SAYS agree with
what the system already KNOWS. It compares extracted values against the
locations, the cadastre and the PostGIS geometry -- three sources that were
populated independently of any OCR.

Rules that hold throughout:

  * A finding never rewrites a value (§44). It reports a disagreement and lets
    an officer decide which side is wrong -- and the document is very often the
    correct side, because the cadastre is itself derived data.
  * A finding is not an accusation (§34). "does not match" and "could not be
    found", never "false" or "fraudulent".
  * An absent value produces no finding. A field the extractor missed is
    already reported as MISSING; saying it also fails to match the cadastre is
    the same fact twice.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dc_field

from geoalchemy2 import Geography
from mrittika_domain.area import UnknownAreaUnit, relative_difference, to_square_metres
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.models import Document, Extraction, Location, Parcel

#: Area disagreement above which a finding is raised, as a fraction of the
#: larger figure. Deliberately generous: a bigha is a regional unit, the
#: cadastre polygons are synthetic, and rounding on the page is common. Only a
#: difference an officer would also call a difference should surface.
AREA_TOLERANCE = 0.25

#: Above this the areas differ by more than rounding can explain.
AREA_SEVERE = 0.50


@dataclass
class CrossFinding:
    check: str
    severity: str            # info | warning
    message: str
    field: str | None = None
    evidence: dict = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "evidence": self.evidence,
        }


def _norm(text: str | None) -> str:
    """NFC, case-folded, stripped of punctuation and spacing.

    Devanagari must be normalised before comparison: the same village name
    composed differently compares unequal byte-for-byte while looking identical
    on screen.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFC", text).strip().casefold()
    return re.sub(r"[\s.,;:।|/\\-]+", "", folded)


def _values(session: Session, document: Document) -> dict[str, str]:
    """Effective value per field -- the correction where one exists."""
    rows = session.execute(
        select(Extraction).where(Extraction.document_id == document.id)
    ).scalars().all()
    out: dict[str, str] = {}
    for row in rows:
        value = row.corrected_value or row.normalized_value
        if value and str(value).strip():
            out[row.field] = str(value).strip()
    return out


def _location_names(location: Location | None) -> set[str]:
    if location is None:
        return set()
    return {_norm(location.name), _norm(location.name_devanagari)} - {""}


def check_village(values: dict, village: Location | None) -> list[CrossFinding]:
    stated = values.get("VILLAGE")
    if not stated or village is None:
        return []
    if _norm(stated) in _location_names(village):
        return []
    return [CrossFinding(
        check="village_matches_location",
        severity="warning",
        field="VILLAGE",
        message=(
            f"The page names the village as '{stated}', but this document is "
            f"filed under '{village.name}'."
        ),
        evidence={"on_page": stated, "on_file": village.name,
                  "location_id": village.external_id},
    )]


def check_ancestry(
    session: Session, values: dict, village: Location | None
) -> list[CrossFinding]:
    """DISTRICT and TEHSIL against the village's place in the hierarchy."""
    findings: list[CrossFinding] = []
    if village is None:
        return findings

    ancestry: dict[str, Location] = {}
    node = village
    seen = 0
    while node is not None and node.parent_id and seen < 8:
        node = session.get(Location, node.parent_id)
        seen += 1
        if node is not None:
            ancestry[node.level.upper()] = node

    for field_name, level in (("TEHSIL", "TEHSIL"), ("DISTRICT", "DISTRICT")):
        stated = values.get(field_name)
        expected = ancestry.get(level)
        if not stated or expected is None:
            continue
        if _norm(stated) in _location_names(expected):
            continue
        findings.append(CrossFinding(
            check=f"{field_name.lower()}_matches_hierarchy",
            severity="warning",
            field=field_name,
            message=(
                f"The page names the {level.lower()} as '{stated}', but the "
                f"village it is filed under sits in '{expected.name}'."
            ),
            evidence={"on_page": stated, "on_file": expected.name},
        ))
    return findings


def check_parcel_exists(
    session: Session, values: dict, village: Location | None
) -> tuple[Parcel | None, list[CrossFinding]]:
    """Does a parcel with this khasra exist in this village?"""
    khasra = values.get("KHASRA")
    if not khasra or village is None:
        return None, []

    parcels = session.execute(
        select(Parcel).where(Parcel.village_id == village.id)
    ).scalars().all()
    match = next((p for p in parcels if _norm(p.khasra_number) == _norm(khasra)), None)
    if match is not None:
        return match, []

    return None, [CrossFinding(
        check="khasra_exists_in_cadastre",
        severity="warning",
        field="KHASRA",
        message=(
            f"No parcel numbered '{khasra}' is recorded in {village.name}. "
            "The page may predate the cadastre, or the number may have been "
            "misread."
        ),
        evidence={"khasra": khasra, "village": village.name,
                  "parcels_in_village": len(parcels)},
    )]


def check_khata(values: dict, parcel: Parcel | None) -> list[CrossFinding]:
    stated = values.get("KHATA")
    if not stated or parcel is None or not parcel.khata_number:
        return []
    if _norm(stated) == _norm(parcel.khata_number):
        return []
    return [CrossFinding(
        check="khata_matches_parcel",
        severity="warning",
        field="KHATA",
        message=(
            f"The page gives khata '{stated}' for this plot; the cadastre "
            f"records '{parcel.khata_number}'."
        ),
        evidence={"on_page": stated, "on_file": parcel.khata_number},
    )]


def check_area(values: dict, parcel: Parcel | None) -> list[CrossFinding]:
    """Stated area against the cadastre's recorded area."""
    stated = values.get("AREA")
    unit = values.get("AREA_UNIT")
    if not stated or parcel is None:
        return []

    try:
        stated_value = float(str(stated).replace(",", ""))
    except ValueError:
        return []  # a non-numeric area is a format problem, already reported

    try:
        # An area with no unit on the page is read in the unit the cadastre
        # records for this plot. That is an assumption, so it is stated in the
        # evidence rather than hidden.
        assumed = unit or parcel.area_unit
        stated_sqm = to_square_metres(stated_value, assumed)
        parcel_sqm = to_square_metres(parcel.area_value, parcel.area_unit)
    except UnknownAreaUnit:
        return []

    difference = relative_difference(stated_sqm, parcel_sqm)
    if difference <= AREA_TOLERANCE:
        return []

    return [CrossFinding(
        check="area_matches_cadastre",
        severity="warning",
        field="AREA",
        message=(
            f"The page states an area of {stated_value} {assumed.lower()}; the "
            f"cadastre records {parcel.area_value} {parcel.area_unit.lower()} "
            f"for this plot -- a difference of {difference:.0%}."
        ),
        evidence={
            "on_page_sqm": round(stated_sqm, 2),
            "on_file_sqm": round(parcel_sqm, 2),
            "relative_difference": round(difference, 4),
            "unit_assumed": unit is None,
            "severe": difference > AREA_SEVERE,
        },
    )]


def check_geometry(session: Session, parcel: Parcel | None) -> list[CrossFinding]:
    """The cadastre's own area against the polygon it stores.

    Not about the document at all -- it checks the reference for internal
    consistency. A mismatch here means every area comparison above is being
    made against a figure the geometry does not support, which an officer
    needs to know before trusting one.
    """
    if parcel is None or parcel.geometry is None:
        return []

    # Cast to geography so ST_Area returns square metres on the sphere. ST_Area
    # on a raw 4326 geometry returns square DEGREES, which is not an area at
    # all and would make every comparison below meaningless.
    measured = session.execute(
        select(func.ST_Area(cast(Parcel.geometry, Geography))).where(
            Parcel.id == parcel.id
        )
    ).scalar()
    if measured is None:
        return []

    try:
        recorded = to_square_metres(parcel.area_value, parcel.area_unit)
    except UnknownAreaUnit:
        return []

    difference = relative_difference(float(measured), recorded)
    if difference <= AREA_TOLERANCE:
        return []

    return [CrossFinding(
        check="cadastre_area_matches_its_geometry",
        severity="info",
        field=None,
        message=(
            "The cadastre's recorded area for this plot differs from the area "
            f"of the boundary it stores by {difference:.0%}. Area comparisons "
            "against this plot should be read with that in mind."
        ),
        evidence={
            "geometry_sqm": round(float(measured), 2),
            "recorded_sqm": round(recorded, 2),
            "relative_difference": round(difference, 4),
        },
    )]


def cross_reference(session: Session, document: Document) -> list[CrossFinding]:
    """Every cross-source check for one document, most specific first."""
    values = _values(session, document)
    if not values:
        return []

    village = session.get(Location, document.village_id) if document.village_id else None
    if village is None and document.parcel_id:
        parcel = session.get(Parcel, document.parcel_id)
        village = session.get(Location, parcel.village_id) if parcel else None

    findings: list[CrossFinding] = []
    findings += check_village(values, village)
    findings += check_ancestry(session, values, village)

    parcel, parcel_findings = check_parcel_exists(session, values, village)
    findings += parcel_findings
    if parcel is None and document.parcel_id:
        parcel = session.get(Parcel, document.parcel_id)

    findings += check_khata(values, parcel)
    findings += check_area(values, parcel)
    findings += check_geometry(session, parcel)
    return findings


__all__ = [
    "AREA_SEVERE", "AREA_TOLERANCE", "CrossFinding", "check_ancestry",
    "check_area", "check_geometry", "check_khata", "check_parcel_exists",
    "check_village", "cross_reference",
]
