"""Area units and the one conversion table (§11).

These constants used to live in services/gis alone, which was fine while only
the cadastre generator converted areas. Cross-referencing a document's stated
area against the parcel it claims needs the same arithmetic on the API side,
and a second copy of a constant like SQM_PER_BIGHA is a copy that can drift --
silently, because both halves would still look self-consistent.

A bigha is not a national unit. 2529.285 m² is the Uttar Pradesh pucca bigha,
which is what this synthetic world is built on; another state's bigha is a
different number, and any real deployment must make this configurable per
revenue circle rather than inherit this constant.
"""

from __future__ import annotations

from .enums import AreaUnit

SQM_PER_BIGHA = 2529.285          # Uttar Pradesh pucca bigha
SQM_PER_HECTARE = 10_000.0
SQM_PER_ACRE = 4046.86
SQM_PER_BISWA = SQM_PER_BIGHA / 20.0

SQM_PER_UNIT: dict[str, float] = {
    AreaUnit.BIGHA: SQM_PER_BIGHA,
    AreaUnit.BISWA: SQM_PER_BISWA,
    AreaUnit.ACRE: SQM_PER_ACRE,
    AreaUnit.HECTARE: SQM_PER_HECTARE,
    AreaUnit.SQUARE_METRE: 1.0,
}


class UnknownAreaUnit(ValueError):
    """The unit is not one this system can convert. Never guess a factor."""


def to_square_metres(value: float, unit: str) -> float:
    """Convert an area to m². Raises rather than assuming a unit."""
    try:
        factor = SQM_PER_UNIT[AreaUnit(str(unit).upper())]
    except (KeyError, ValueError) as exc:
        raise UnknownAreaUnit(f"no conversion for area unit {unit!r}") from exc
    return value * factor


def relative_difference(a_sqm: float, b_sqm: float) -> float:
    """Difference between two areas as a fraction of the larger.

    Fraction of the LARGER, not of the first: the measure must be symmetric, or
    'the document is 40% off the parcel' and 'the parcel is 40% off the
    document' would be different findings about the same discrepancy.
    """
    larger = max(abs(a_sqm), abs(b_sqm))
    if larger == 0:
        return 0.0
    return abs(a_sqm - b_sqm) / larger


__all__ = [
    "SQM_PER_ACRE", "SQM_PER_BIGHA", "SQM_PER_BISWA", "SQM_PER_HECTARE",
    "SQM_PER_UNIT", "UnknownAreaUnit", "relative_difference", "to_square_metres",
]
