"""Name and vocabulary pools for synthetic North Indian land records.

Entirely invented combinations. No pool entry is drawn from a real land record,
and generated people are not intended to correspond to anyone (§83).
"""

GIVEN_NAMES_MASCULINE = [
    "राम प्रसाद", "श्याम लाल", "हरि शंकर", "मोहन", "गिरधारी",
    "बृजेश", "सुरेश", "रमेश", "दीनदयाल", "कैलाश",
    "जगदीश", "ओम प्रकाश", "बाबूराम", "छोटेलाल", "रघुनाथ",
]

GIVEN_NAMES_FEMININE = [
    "सीमा", "कमला", "सरोज", "गीता", "शांति",
    "उर्मिला", "पुष्पा", "राजकुमारी", "मुन्नी", "विद्या",
]

SURNAMES = [
    "सिंह", "देवी", "यादव", "वर्मा", "शर्मा",
    "गुप्ता", "पाल", "मौर्य", "कुशवाहा", "तिवारी",
]

#: Land classification as written on the document.
LAND_CLASSES = [
    "सिंचित",      # irrigated
    "असिंचित",     # unirrigated
    "बंजर",        # barren
    "चारागाह",     # pasture
    "आबादी",       # habitation
]

#: Area unit as written, mapped to the AreaUnit enum value.
AREA_UNITS_RAW = {
    "BIGHA": "बीघा",
    "BISWA": "बिस्वा",
    "HECTARE": "हेक्टेयर",
    "ACRE": "एकड़",
}

#: Village names for the slice-1 tehsil.
VILLAGES = [
    ("रामपुर", "Rampur"),
    ("मुड़ियाकला", "Mudiyakala"),
    ("बरगदही", "Bargadahi"),
    ("सोनवर्षा", "Sonwarsha"),
]

DISTRICT = ("डेमो जिला", "Demo District")
TEHSIL = ("डेमो तहसील", "Demo Tehsil")
STATE = ("उत्तर प्रदेश", "Uttar Pradesh")
COUNTRY = ("भारत", "India")

#: A second state, so state-wise and district-wise progress have something to
#: compare. Bihar because its records are Hindi khasras too; its tehsil-level
#: unit is the anchal (circle).
SECOND_STATE = ("बिहार", "Bihar")
SECOND_DISTRICT = ("नमूना जिला", "Sample District")
SECOND_TEHSIL = ("नमूना अंचल", "Sample Anchal")
SECOND_VILLAGES = [
    ("सरैया", "Saraiya"),
    ("कटरा", "Katra"),
]

#: Devanagari digits, for rendering numbers as they appear on legacy documents.
DEVANAGARI_DIGITS = "०१२३४५६७८९"


def to_devanagari_digits(text: str) -> str:
    """'142/2' -> '१४२/२'. Used when rendering, never when storing."""
    return "".join(DEVANAGARI_DIGITS[int(c)] if c.isdigit() else c for c in text)


def from_devanagari_digits(text: str) -> str:
    """'१४२/२' -> '142/2'. The normalization step the extractor must perform."""
    table = {d: str(i) for i, d in enumerate(DEVANAGARI_DIGITS)}
    return "".join(table.get(c, c) for c in text)
