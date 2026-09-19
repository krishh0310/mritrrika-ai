"""Fields are extracted from Telugu, Tamil and Kannada forms, not only Hindi.

OCR could already read these scripts -- Gemini reads any script, and PaddleOCR
ships te/ta/ka recognisers -- but the extractor searched every page for Hindi
labels, so a correctly read Telugu Pahani produced no fields at all. Each test
here lays out a page the way that state's record does, in OCR blocks, and
checks the extractor pulls the same canonical fields it pulls from a Khasra.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

from extraction.field_extractor import extract  # noqa: E402
from extraction.labels import LABELS_BY_LANGUAGE  # noqa: E402
from mrittika_domain.area import SQM_PER_ACRE, to_square_metres  # noqa: E402
from normalization.normalizers import (  # noqa: E402
    normalize_field,
    normalize_unit,
    to_ascii_digits,
)
from ocr.provider import TextBlock  # noqa: E402


def page(header: list[tuple[str, str]], owner_heading: str, share_heading: str,
         owners: list[tuple[str, str]], footer: str) -> list[TextBlock]:
    """A two-column header of label/value pairs, then an owners table."""
    blocks: list[TextBlock] = []
    y = 100
    for label, value in header:
        blocks.append(TextBlock(label, 0.95, (80, y, 260, y + 34)))
        blocks.append(TextBlock(value, 0.93, (300, y, 520, y + 34)))
        y += 50
    y += 20
    blocks.append(TextBlock(owner_heading, 0.95, (90, y, 330, y + 34)))
    blocks.append(TextBlock(share_heading, 0.95, (640, y, 700, y + 34)))
    y += 50
    for name, share in owners:
        blocks.append(TextBlock(name, 0.92, (90, y, 330, y + 34)))
        blocks.append(TextBlock(share, 0.92, (645, y, 695, y + 34)))
        y += 40
    blocks.append(TextBlock(footer, 0.9, (70, y + 10, 420, y + 44)))
    return blocks


TELUGU = page(
    header=[
        ("జిల్లా", "రంగారెడ్డి"),
        ("మండలం", "శంకర్‌పల్లి"),
        ("గ్రామం", "మోకిల"),
        ("ఖాతా సంఖ్య", "౨౧౭"),
        ("సర్వే నంబరు", "౧౪౨/౨"),
        ("విస్తీర్ణం", "౩.౨౦ ఎకరాలు"),
    ],
    owner_heading="పట్టాదారు పేరు",
    share_heading="వాటా",
    owners=[("కొండా రమేష్", "౧/౨"), ("కొండా లక్ష్మి", "౧/౨")],
    footer="గమనిక: డిజిటలీకరణ కోసం",
)

TAMIL = page(
    header=[
        ("மாவட்டம்", "சேலம்"),
        ("வட்டம்", "ஆத்தூர்"),
        ("கிராமம்", "தலைவாசல்"),
        ("பட்டா எண்", "௪௫௬"),
        ("புல எண்", "௮௯/௩"),
        ("பரப்பளவு", "௧.௫ ஏக்கர்"),
    ],
    owner_heading="உரிமையாளர் பெயர்",
    share_heading="பங்கு",
    owners=[("முருகன் செல்வம்", "௧")],
    footer="குறிப்பு: கணினிமயமாக்கலுக்காக",
)

KANNADA = page(
    header=[
        ("ಜಿಲ್ಲೆ", "ಮಂಡ್ಯ"),
        ("ತಾಲ್ಲೂಕು", "ಮದ್ದೂರು"),
        ("ಗ್ರಾಮ", "ಕೆಸ್ತೂರು"),
        ("ಖಾತೆ ಸಂಖ್ಯೆ", "೩೩"),
        ("ಸರ್ವೆ ನಂಬರ್", "೫೭/೧"),
        ("ವಿಸ್ತೀರ್ಣ", "೨ ಎಕರೆ"),
    ],
    owner_heading="ಖಾತೆದಾರರ ಹೆಸರು",
    share_heading="ಪಾಲು",
    owners=[("ಬಸವರಾಜು ಗೌಡ", "೧/೩"), ("ನಾಗಮ್ಮ", "೨/೩")],
    footer="ಷರಾ: ಗಣಕೀಕರಣಕ್ಕಾಗಿ",
)

BENGALI = page(
    header=[("জেলা", "নদিয়া"), ("ব্লক", "হাঁসখালি"), ("মৌজা", "বগুলা"),
            ("খতিয়ান নং", "৩১২"), ("দাগ নং", "৭৪/২"), ("জমির পরিমাণ", "১.২ একর")],
    owner_heading="রায়তের নাম", share_heading="অংশ",
    owners=[("সুবীর মণ্ডল", "১/২"), ("রীতা মণ্ডল", "১/২")],
    footer="মন্তব্য: ডিজিটাইজেশনের জন্য",
)
GUJARATI = page(
    header=[("જિલ્લો", "આણંદ"), ("તાલુકો", "પેટલાદ"), ("ગામ", "સોજિત્રા"),
            ("ખાતા નંબર", "૧૫૮"), ("સર્વે નંબર", "૪૪૧/૩"), ("ક્ષેત્રફળ", "૨.૫ એકર")],
    owner_heading="ખાતેદારનું નામ", share_heading="હિસ્સો",
    owners=[("રમેશભાઈ પટેલ", "૧")],
    footer="નોંધ: ડિજિટાઇઝેશન માટે",
)
PUNJABI = page(
    header=[("ਜ਼ਿਲ੍ਹਾ", "ਲੁਧਿਆਣਾ"), ("ਤਹਿਸੀਲ", "ਜਗਰਾਉਂ"), ("ਪਿੰਡ", "ਸਿੱਧਵਾਂ"),
            ("ਖੇਵਟ ਨੰ", "੭੭"), ("ਖਸਰਾ ਨੰ", "੨੧੩/੧"), ("ਰਕਬਾ", "੩ ਏਕੜ")],
    owner_heading="ਮਾਲਕ ਦਾ ਨਾਮ", share_heading="ਹਿੱਸਾ",
    owners=[("ਗੁਰਪ੍ਰੀਤ ਸਿੰਘ", "੧/੨"), ("ਹਰਜੀਤ ਕੌਰ", "੧/੨")],
    footer="ਕੈਫੀਅਤ: ਡਿਜੀਟਾਈਜ਼ੇਸ਼ਨ ਲਈ",
)
ODIA = page(
    header=[("ଜିଲ୍ଲା", "ପୁରୀ"), ("ତହସିଲ", "ପିପିଲି"), ("ମୌଜା", "ରଘୁରାଜପୁର"),
            ("ଖାତା ନଂ", "୯୨"), ("ପ୍ଲଟ ନଂ", "୫୬୭/୨"), ("ରକବା", "୦.୮ ଏକର")],
    owner_heading="ରୟତଙ୍କ ନାମ", share_heading="ଅଂଶ",
    owners=[("ବିଶ୍ୱନାଥ ମହାପାତ୍ର", "୧")],
    footer="ମନ୍ତବ୍ୟ: ଡିଜିଟାଇଜେସନ ପାଇଁ",
)
MALAYALAM = page(
    header=[("ജില്ല", "തൃശൂർ"), ("താലൂക്ക്", "ചാവക്കാട്"), ("വില്ലേജ്", "ഗുരുവായൂർ"),
            ("തണ്ടപ്പേര് നമ്പർ", "൧൨൩"), ("സർവ്വേ നമ്പർ", "൮൯/൪"), ("വിസ്തീർണ്ണം", "൫൦ സെന്റ്")],
    owner_heading="ഉടമയുടെ പേര്", share_heading="ഓഹരി",
    owners=[("രാജൻ നായർ", "൧")],
    footer="കുറിപ്പ്: ഡിജിറ്റൈസേഷനായി",
)

CASES = {
    "telugu": (TELUGU, {
        # The zero-width non-joiner in the page's spelling is canonicalised
        # away, exactly as the Hindi path already does -- see below.
        "DISTRICT": "రంగారెడ్డి", "TEHSIL": "శంకర్పల్లి", "VILLAGE": "మోకిల",
        "KHATA": "217", "KHASRA": "142/2", "AREA": "3.2",
    }, ["కొండా రమేష్", "కొండా లక్ష్మి"], ["1/2", "1/2"]),
    "tamil": (TAMIL, {
        "DISTRICT": "சேலம்", "TEHSIL": "ஆத்தூர்", "VILLAGE": "தலைவாசல்",
        "KHATA": "456", "KHASRA": "89/3", "AREA": "1.5",
    }, ["முருகன் செல்வம்"], ["1/1"]),
    "kannada": (KANNADA, {
        "DISTRICT": "ಮಂಡ್ಯ", "TEHSIL": "ಮದ್ದೂರು", "VILLAGE": "ಕೆಸ್ತೂರು",
        "KHATA": "33", "KHASRA": "57/1", "AREA": "2",
    }, ["ಬಸವರಾಜು ಗೌಡ", "ನಾಗಮ್ಮ"], ["1/3", "2/3"]),
    # Read by Gemini vision in production; PaddleOCR has no model for these.
    "bengali": (BENGALI, {
        "DISTRICT": "নদিয়া", "TEHSIL": "হাঁসখালি", "VILLAGE": "বগুলা",
        "KHATA": "312", "KHASRA": "74/2", "AREA": "1.2",
    }, ["সুবীর মণ্ডল", "রীতা মণ্ডল"], ["1/2", "1/2"]),
    "gujarati": (GUJARATI, {
        "DISTRICT": "આણંદ", "TEHSIL": "પેટલાદ", "VILLAGE": "સોજિત્રા",
        "KHATA": "158", "KHASRA": "441/3", "AREA": "2.5",
    }, ["રમેશભાઈ પટેલ"], ["1/1"]),
    "punjabi": (PUNJABI, {
        "DISTRICT": "ਲੁਧਿਆਣਾ", "TEHSIL": "ਜਗਰਾਉਂ", "VILLAGE": "ਸਿੱਧਵਾਂ",
        "KHATA": "77", "KHASRA": "213/1", "AREA": "3",
    }, ["ਗੁਰਪ੍ਰੀਤ ਸਿੰਘ", "ਹਰਜੀਤ ਕੌਰ"], ["1/2", "1/2"]),
    "odia": (ODIA, {
        "DISTRICT": "ପୁରୀ", "TEHSIL": "ପିପିଲି", "VILLAGE": "ରଘୁରାଜପୁର",
        "KHATA": "92", "KHASRA": "567/2", "AREA": "0.8",
    }, ["ବିଶ୍ୱନାଥ ମହାପାତ୍ର"], ["1/1"]),
    "malayalam": (MALAYALAM, {
        "DISTRICT": "തൃശൂർ", "TEHSIL": "ചാവക്കാട്", "VILLAGE": "ഗുരുവായൂർ",
        "KHATA": "123", "KHASRA": "89/4", "AREA": "50",
    }, ["രാജൻ നായർ"], ["1/1"]),
}


def normalised(result, field):
    return [normalize_field(v.field, v.raw_value) for v in result.by_field(field)]


@pytest.mark.parametrize("language", CASES)
def test_header_fields_are_extracted_and_normalised(language):
    blocks, expected, _owners, _shares = CASES[language]
    result = extract(blocks, page_width=1240)

    for field, value in expected.items():
        assert normalised(result, field) == [value], (language, field)
    assert result.missing == []


@pytest.mark.parametrize("language", CASES)
def test_owners_table_is_read_and_stops_at_the_remark(language):
    blocks, _expected, owners, shares = CASES[language]
    result = extract(blocks, page_width=1240)

    # The remark line under the table is not one more owner.
    assert normalised(result, "OWNER") == owners
    assert normalised(result, "SHARE") == shares


def test_tamil_district_and_taluk_labels_do_not_collide():
    """வட்டம் (taluk) is a substring of மாவட்டம் (district) and scores 0.86
    against it -- the stronger exact match must keep the district's value."""
    result = extract(TAMIL, page_width=1240)
    assert normalised(result, "DISTRICT") == ["சேலம்"]
    assert normalised(result, "TEHSIL") == ["ஆத்தூர்"]


def test_every_language_names_the_same_fields():
    """A field one language can extract and another cannot is a silent gap."""
    fields = {lang: set(labels) for lang, labels in LABELS_BY_LANGUAGE.items()}
    assert len({frozenset(f) for f in fields.values()}) == 1, fields


def test_hindi_extraction_is_unchanged_by_the_merge():
    blocks = page(
        header=[("जिला", "डेमो जिला"), ("तहसील", "डेमो तहसील"), ("ग्राम", "रामपुर"),
                ("खसरा सं", "१४२/२"), ("क्षेत्रफल", "२.७५ बीघा")],
        owner_heading="खातेदार का नाम", share_heading="अंश",
        owners=[("गिरधारी देवी", "१/२")], footer="टिप्पणी: अभिलेख डिजिटलीकरण हेतु",
    )
    result = extract(blocks, page_width=1240)
    assert normalised(result, "VILLAGE") == ["रामपुर"]
    assert normalised(result, "KHASRA") == ["142/2"]
    assert normalised(result, "OWNER") == ["गिरधारी देवी"]


@pytest.mark.parametrize("native, ascii_", [
    ("१४२/२", "142/2"), ("౧౪౨/౨", "142/2"), ("௧௪௨/௨", "142/2"), ("೧೪೨/೨", "142/2"),
    ("১৪২/২", "142/2"), ("૧૪૨/૨", "142/2"), ("੧੪੨/੨", "142/2"), ("୧୪୨/୨", "142/2"),
    ("൧൪൨/൨", "142/2"),
])
def test_native_digits_in_every_script_become_ascii(native, ascii_):
    assert to_ascii_digits(native) == ascii_


@pytest.mark.parametrize("text, unit", [
    ("౩.౨౦ ఎకరాలు", "ACRE"), ("10 గుంటలు", "GUNTHA"), ("50 సెంట్లు", "CENT"),
    ("௧.௫ ஏக்கர்", "ACRE"), ("40 சென்ட்", "CENT"),
    ("೨ ಎಕರೆ", "ACRE"), ("20 ಗುಂಟೆ", "GUNTHA"),
    ("२.७५ बीघा", "BIGHA"),
    ("১.২ একর", "ACRE"), ("৪০ শতক", "CENT"), ("૨.૫ એકર", "ACRE"), ("੩ ਏਕੜ", "ACRE"),
    ("୦.୮ ଏକର", "ACRE"), ("୫୦ ଡେସିମିଲ", "CENT"), ("൫൦ സെന്റ്", "CENT"),
])
def test_unit_words_in_every_language(text, unit):
    assert normalize_unit(text) == unit


def test_southern_units_convert_as_fractions_of_the_acre():
    assert to_square_metres(40, "GUNTHA") == pytest.approx(SQM_PER_ACRE)
    assert to_square_metres(100, "CENT") == pytest.approx(SQM_PER_ACRE)


def test_joiner_variants_of_one_name_canonicalise_together():
    """OCR emits a Telugu name with or without the zero-width non-joiner; the
    two must compare equal or a village fails to match its own record."""
    with_joiner = normalize_field("TEHSIL", "శంకర్\u200cపల్లి")
    without = normalize_field("TEHSIL", "శంకర్పల్లి")
    assert with_joiner == without


def test_a_bare_vowel_sign_is_still_not_a_value():
    """Generalising the plausibility check to every script must not let a
    lone combining mark through as a value."""
    from extraction.field_extractor import _plausible_value

    for fragment in ("ि", "్", "ு", "ೆ"):
        assert not _plausible_value(fragment + fragment)
    assert _plausible_value("మోకిల")


def test_auto_routing_picks_the_recogniser_that_reads_its_own_script():
    """OCR_LANG=auto: every candidate reads the page, and the one whose output
    is confidently in its own script wins. The Devanagari model handed a Telugu
    page returns Latin-ish noise, which scores near zero however sure it is."""
    import numpy as np
    from ocr.provider import OcrResult, RoutedPaddleProvider

    class Fake:
        def __init__(self, text, confidence):
            self.text, self.confidence = text, confidence

        def recognize(self, image):
            return OcrResult(blocks=[TextBlock(self.text, self.confidence, (0, 0, 9, 9))])

    provider = RoutedPaddleProvider(candidates=("hi", "te"))
    # Pre-seeded cache: routing must reuse loaded engines, never rebuild them.
    provider._providers = {"hi": Fake("008 28s", 0.9), "te": Fake("సర్వే నంబరు", 0.8)}

    result = provider.recognize(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.provider == "paddle:te"
    assert provider.last_decision.lang == "te"
