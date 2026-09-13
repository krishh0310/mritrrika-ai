"""A record extract a citizen can download, print and have checked (§15).

Three decisions worth stating, because each rules out the obvious approach.

**Not reportlab.** ReportLab does not shape Devanagari: it places glyphs
left-to-right without applying the substitutions Indic scripts need, so
conjuncts break apart and matras land next to the wrong consonant. A land
record rendered that way is not merely ugly -- it says something different from
what it claims to say. The certificate is drawn with Pillow, which this project
already requires to be libraqm-linked for exactly this reason, and saved as a
PDF from there.

**The QR does not carry the record.** A QR containing the record's contents is
a record that can be edited by regenerating a QR. It carries a URL and a
content hash, so verifying means asking THIS system whether a certificate with
that hash was issued for that parcel. The paper cannot vouch for itself.

**Verification returns match-or-not, never content.** Anyone holding a printed
certificate can check it. If the check replied with the record, the QR would
become a way to read a stranger's holdings off a photograph of their paperwork
(§17, §18).
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Parcel
from app.repositories import ownership_repository

#: The libraqm-shaped Devanagari faces the dataset generator already uses.
#: Listed in preference order; the first that loads wins.
DEVANAGARI_FONTS = (
    "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    "/System/Library/Fonts/Supplemental/Kohinoor.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
)

#: A4 at 150 dpi. Big enough that the QR survives a phone camera, small enough
#: that the PDF stays well under a megabyte.
PAGE = (1240, 1754)
MARGIN = 90

INK = (26, 26, 26)
MUTED = (79, 74, 64)
RULE = (205, 197, 178)
WARN = (166, 29, 24)


class CertificateError(Exception):
    pass


@dataclass(frozen=True)
class Certificate:
    parcel_id: str
    content_hash: str
    issued_at: str
    pdf: bytes

    def to_dict(self) -> dict:
        return {
            "parcel_id": self.parcel_id,
            "content_hash": self.content_hash,
            "issued_at": self.issued_at,
            "is_synthetic": True,
        }


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = DEVANAGARI_FONTS[::-1] if bold else DEVANAGARI_FONTS
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # Pillow's default bitmap font cannot draw Devanagari at all. Falling back
    # to it silently would produce a certificate of empty boxes, so this is an
    # error the caller must see.
    raise CertificateError(
        "no Devanagari-capable font found; install Noto Sans Devanagari "
        "(see DEVANAGARI_FONTS)"
    )


def content_of(session: Session, parcel: Parcel) -> dict:
    """Exactly what the certificate asserts, in a stable shape.

    This dict is what gets hashed, so key order and formatting are part of the
    contract: re-serialising it differently later would invalidate every
    certificate already printed.
    """
    holders = [
        row for row in ownership_repository.ownership_history(session, parcel.id)
        if row.get("valid_to") in (None, "")
    ]
    return {
        "parcel_id": parcel.external_id,
        "khasra_number": parcel.khasra_number,
        "khata_number": parcel.khata_number,
        "village": parcel.village.name if parcel.village else None,
        "village_devanagari": parcel.village.name_devanagari if parcel.village else None,
        "area_value": parcel.area_value,
        "area_unit": parcel.area_unit,
        "land_class": parcel.land_class,
        "holders": [
            {"owner": h.get("owner"), "share": h.get("share"),
             "since": str(h.get("valid_from"))}
            for h in holders
        ],
    }


def hash_of(content: dict) -> str:
    """SHA-256 over a canonical serialisation.

    sort_keys and a fixed separator, so two runs over the same record produce
    the same hash regardless of dict ordering; ensure_ascii=False so the
    Devanagari is hashed as itself rather than as escape sequences.
    """
    canonical = json.dumps(
        content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _qr_image(payload: str, box: int = 6):
    import qrcode

    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box,
        border=2,
    )
    code.add_data(payload)
    code.make(fit=True)
    return code.make_image(fill_color="black", back_color="white").convert("RGB")


def render(content: dict, *, verify_url: str, issued_at: str) -> bytes:
    """Draw the certificate and return it as PDF bytes."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", PAGE, "white")
    draw = ImageDraw.Draw(page)

    title = _font(44, bold=True)
    label = _font(24)
    value = _font(28)
    small = _font(20)

    y = MARGIN
    draw.text((MARGIN, y), "भू-अभिलेख विवरण", font=title, fill=INK)
    y += 58
    draw.text((MARGIN, y), "Record of Rights — extract", font=_font(26), fill=MUTED)
    y += 52

    # The notice is placed above the data, not in a footer. A reader who stops
    # reading should already have seen it.
    draw.rectangle([MARGIN, y, PAGE[0] - MARGIN, y + 46], outline=WARN, width=2)
    draw.text(
        (MARGIN + 14, y + 11),
        "DEMO / SYNTHETIC DATA — not a real land record",
        font=small, fill=WARN,
    )
    y += 74
    draw.line([MARGIN, y, PAGE[0] - MARGIN, y], fill=RULE, width=2)
    y += 34

    rows = [
        ("भूखंड / Parcel", content["parcel_id"]),
        ("खसरा संख्या / Khasra", content["khasra_number"]),
        ("खाता संख्या / Khata", content["khata_number"] or "—"),
        ("ग्राम / Village",
         content.get("village_devanagari") or content.get("village") or "—"),
        ("क्षेत्रफल / Area",
         f"{content['area_value']} {str(content['area_unit'] or '').lower()}"),
        ("भूमि श्रेणी / Land class", content["land_class"] or "—"),
    ]
    for name, text in rows:
        draw.text((MARGIN, y), name, font=label, fill=MUTED)
        draw.text((MARGIN + 430, y - 3), str(text), font=value, fill=INK)
        y += 52

    y += 18
    draw.line([MARGIN, y, PAGE[0] - MARGIN, y], fill=RULE, width=2)
    y += 30
    draw.text((MARGIN, y), "वर्तमान धारक / Current holders", font=label, fill=MUTED)
    y += 44

    if content["holders"]:
        for holder in content["holders"]:
            draw.text((MARGIN + 20, y), str(holder["owner"]), font=value, fill=INK)
            draw.text((MARGIN + 700, y + 3),
                      f"हिस्सा {holder['share']}", font=label, fill=MUTED)
            y += 46
    else:
        draw.text((MARGIN + 20, y), "—", font=value, fill=INK)
        y += 46

    # QR bottom-right, with the hash printed beside it: a phone reads the QR, a
    # person without one can still compare the hash by eye.
    qr = _qr_image(verify_url)
    qr_size = 300
    qr = qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    qr_x = PAGE[0] - MARGIN - qr_size
    qr_y = PAGE[1] - MARGIN - qr_size - 90
    page.paste(qr, (qr_x, qr_y))
    draw.text((qr_x, qr_y + qr_size + 10), "Scan to verify this extract",
              font=small, fill=MUTED)

    footer = PAGE[1] - MARGIN - 70
    draw.line([MARGIN, footer - 20, PAGE[0] - MARGIN, footer - 20], fill=RULE, width=2)
    draw.text((MARGIN, footer), f"Issued {issued_at}", font=small, fill=MUTED)
    # ASCII ellipsis: the Devanagari faces have no U+2026 glyph, so "…" draws
    # as a tofu box on the one line a reader is meant to compare by eye.
    draw.text((MARGIN, footer + 28),
              f"Content hash {content['_hash'][:32]}...", font=small, fill=MUTED)

    buffer = io.BytesIO()
    page.save(buffer, format="PDF", resolution=150.0)
    return buffer.getvalue()


def issue(session: Session, parcel: Parcel, *, base_url: str) -> Certificate:
    """Build the certificate for one parcel the caller may already see."""
    content = content_of(session, parcel)
    digest = hash_of(content)
    issued_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    verify_url = (
        f"{base_url.rstrip('/')}/verify"
        f"?parcel={content['parcel_id']}&hash={digest}"
    )
    pdf = render({**content, "_hash": digest},
                 verify_url=verify_url, issued_at=issued_at)
    return Certificate(
        parcel_id=content["parcel_id"], content_hash=digest,
        issued_at=issued_at, pdf=pdf,
    )


def verify(session: Session, parcel_external_id: str, digest: str) -> dict:
    """Does a certificate with this hash describe this parcel, as it stands now?

    Returns match-or-not and nothing about the record. A reply carrying the
    record would turn a photograph of someone's paperwork into a way to read
    their holdings (§17).
    """
    parcel = session.query(Parcel).filter(
        Parcel.external_id == parcel_external_id
    ).one_or_none()
    if parcel is None:
        return {
            "parcel_id": parcel_external_id,
            "matches": False,
            "reason": "no such parcel",
            "is_synthetic": True,
        }

    current = hash_of(content_of(session, parcel))
    matches = bool(digest) and current == digest
    return {
        "parcel_id": parcel_external_id,
        "matches": matches,
        # Said plainly: a record legitimately changes when a mutation is
        # approved, so a mismatch is "out of date", not "forged" (§34).
        "reason": (
            "this extract matches the record as it stands"
            if matches else
            "this extract does not match the current record; it may predate a "
            "mutation, or it may not have been issued by this system"
        ),
        "is_synthetic": True,
    }


__all__ = [
    "Certificate", "CertificateError", "content_of", "hash_of", "issue",
    "render", "verify",
]
