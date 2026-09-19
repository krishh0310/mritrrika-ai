"""Printed form vocabulary, per language (§6).

The extractor is label-anchored: it finds the printed word for a field and
reads the value beside or beneath it. So the set of printed words it knows IS
the set of languages it can extract from. OCR reading a Telugu page correctly
is worth nothing if the extractor then searches that page for 'खसरा'.

Each language names the same canonical fields, in the wording its own revenue
records use -- not a translation of the Hindi form:

    hi  Khasra / Khatauni (Uttar Pradesh)     village, tehsil, khasra number
    te  Pahani / Adangal, 1-B ROR (AP, TG)    grama, mandalam, survey number
    ta  Chitta / Adangal (Tamil Nadu)         kiramam, vattam, pula en
    kn  Pahani / RTC (Karnataka)              grama, taluk, survey number
    bn  Khatian / Parcha (West Bengal)        mouza, block, dag number
    gu  7/12 Utara (Gujarat)                  gam, taluko, survey number
    pa  Jamabandi (Punjab)                    pind, tehsil, khasra, khewat
    or  Record of Rights (Odisha)             mouza, tahasil, plot number
    ml  Thandaper (Kerala)                    village, taluk, survey number

PaddleOCR has no recogniser for the last five scripts, so they are read by the
Gemini vision provider; everything after OCR is the same for all nine.

A survey number is what the south calls the parcel number the north calls a
khasra, so both map to KHASRA; a patta number is the holding, so it maps to
KHATA. Mandal (te) and taluk/vattam (ta, kn) sit where the tehsil sits in the
revenue hierarchy, so they map to TEHSIL.

Merging the languages into one lookup is safe because the scripts occupy
disjoint Unicode blocks: a Telugu block scores 0.0 against a Devanagari label,
so no label from one language can fuzzily match text in another. That is also
why no per-page language switch is needed -- a mixed page (a Telugu form with
Devanagari stamps) is handled by the same lookup.
"""

from __future__ import annotations

#: Language code -> field -> label spellings. Several spellings per field
#: because forms genuinely vary (जिला vs जनपद, ग्राम vs मौजा) and because
#: fuzzy matching is anchored on the closest one.
LABELS_BY_LANGUAGE: dict[str, dict[str, list[str]]] = {
    "hi": {
        "DISTRICT": ["जिला", "जनपद"],
        "TEHSIL": ["तहसील"],
        "VILLAGE": ["ग्राम", "मौजा", "ग्राम / मौजा"],
        "RECORD_YEAR": ["फसली वर्ष", "वर्ष"],
        "KHATA": ["खाता सं", "खाता संख्या", "खाता"],
        "KHASRA": ["खसरा सं", "खसरा संख्या", "खसरा"],
        "AREA": ["क्षेत्रफल"],
        "LAND_CLASS": ["भूमि श्रेणी", "श्रेणी"],
        "MUTATION": ["नामांतरण सं", "नामांतरण संख्या"],
        "DATE": ["दिनांक"],
        "GUARDIAN": ["पिता / पति", "पिता", "पति"],
    },
    "te": {
        "DISTRICT": ["జిల్లా"],
        "TEHSIL": ["మండలం", "తహసీల్"],
        "VILLAGE": ["గ్రామం", "రెవెన్యూ గ్రామం"],
        "RECORD_YEAR": ["ఫసలీ సంవత్సరం", "సంవత్సరం"],
        "KHATA": ["ఖాతా సంఖ్య", "ఖాతా నం", "ఖాతా"],
        "KHASRA": ["సర్వే నంబరు", "సర్వే సంఖ్య", "సర్వే నం"],
        "AREA": ["విస్తీర్ణం"],
        "LAND_CLASS": ["భూమి వర్గీకరణ", "భూమి రకం"],
        "MUTATION": ["మ్యుటేషన్ సంఖ్య", "మ్యుటేషన్ నం"],
        "DATE": ["తేదీ"],
        "GUARDIAN": ["తండ్రి / భర్త", "తండ్రి పేరు", "తండ్రి", "భర్త"],
    },
    "ta": {
        "DISTRICT": ["மாவட்டம்"],
        "TEHSIL": ["வட்டம்", "தாலுகா"],
        "VILLAGE": ["கிராமம்", "வருவாய் கிராமம்"],
        "RECORD_YEAR": ["பசலி ஆண்டு", "ஆண்டு"],
        "KHATA": ["பட்டா எண்", "பட்டா"],
        "KHASRA": ["புல எண்", "சர்வே எண்"],
        "AREA": ["பரப்பளவு", "பரப்பு"],
        "LAND_CLASS": ["நில வகை"],
        "MUTATION": ["பெயர் மாற்ற எண்"],
        "DATE": ["தேதி"],
        "GUARDIAN": ["தந்தை / கணவர்", "தந்தை பெயர்", "தந்தை", "கணவர்"],
    },
    "kn": {
        "DISTRICT": ["ಜಿಲ್ಲೆ"],
        "TEHSIL": ["ತಾಲ್ಲೂಕು", "ತಾಲೂಕು"],
        "VILLAGE": ["ಗ್ರಾಮ"],
        "RECORD_YEAR": ["ವರ್ಷ"],
        "KHATA": ["ಖಾತೆ ಸಂಖ್ಯೆ", "ಖಾತೆ ನಂ", "ಖಾತೆ"],
        "KHASRA": ["ಸರ್ವೆ ನಂಬರ್", "ಸರ್ವೆ ಸಂಖ್ಯೆ", "ಸರ್ವೆ ನಂ"],
        "AREA": ["ವಿಸ್ತೀರ್ಣ"],
        "LAND_CLASS": ["ಭೂಮಿಯ ವರ್ಗ", "ಜಮೀನಿನ ವರ್ಗ"],
        "MUTATION": ["ಮ್ಯುಟೇಶನ್ ಸಂಖ್ಯೆ", "ಎಂ.ಆರ್ ಸಂಖ್ಯೆ"],
        "DATE": ["ದಿನಾಂಕ"],
        "GUARDIAN": ["ತಂದೆ / ಗಂಡ", "ತಂದೆಯ ಹೆಸರು", "ತಂದೆ", "ಗಂಡ"],
    },
    "bn": {
        "DISTRICT": ["জেলা"],
        "TEHSIL": ["ব্লক", "থানা"],
        "VILLAGE": ["মৌজা", "গ্রাম"],
        "RECORD_YEAR": ["সাল", "বছর"],
        "KHATA": ["খতিয়ান নং", "খতিয়ান"],
        "KHASRA": ["দাগ নং", "দাগ"],
        "AREA": ["জমির পরিমাণ", "পরিমাণ"],
        "LAND_CLASS": ["জমির শ্রেণী", "শ্রেণী"],
        "MUTATION": ["মিউটেশন নং"],
        "DATE": ["তারিখ"],
        "GUARDIAN": ["পিতা / স্বামী", "পিতা", "স্বামী"],
    },
    "gu": {
        "DISTRICT": ["જિલ્લો"],
        "TEHSIL": ["તાલુકો"],
        "VILLAGE": ["ગામ"],
        "RECORD_YEAR": ["વર્ષ"],
        "KHATA": ["ખાતા નંબર", "ખાતા નં"],
        "KHASRA": ["સર્વે નંબર", "સર્વે નં", "બ્લોક નંબર"],
        "AREA": ["ક્ષેત્રફળ"],
        "LAND_CLASS": ["જમીનનો પ્રકાર"],
        "MUTATION": ["ફેરફાર નોંધ નં"],
        "DATE": ["તારીખ"],
        "GUARDIAN": ["પિતા / પતિ", "પિતા", "પતિ"],
    },
    "pa": {
        "DISTRICT": ["ਜ਼ਿਲ੍ਹਾ", "ਜਿਲ੍ਹਾ"],
        "TEHSIL": ["ਤਹਿਸੀਲ"],
        "VILLAGE": ["ਪਿੰਡ"],
        "RECORD_YEAR": ["ਸਾਲ"],
        "KHATA": ["ਖੇਵਟ ਨੰ", "ਖੇਵਟ"],
        "KHASRA": ["ਖਸਰਾ ਨੰ", "ਖਸਰਾ"],
        "AREA": ["ਰਕਬਾ"],
        "LAND_CLASS": ["ਕਿਸਮ ਜ਼ਮੀਨ"],
        "MUTATION": ["ਇੰਤਕਾਲ ਨੰ"],
        "DATE": ["ਮਿਤੀ"],
        "GUARDIAN": ["ਪਿਤਾ / ਪਤੀ", "ਪਿਤਾ", "ਪਤੀ"],
    },
    "or": {
        "DISTRICT": ["ଜିଲ୍ଲା"],
        "TEHSIL": ["ତହସିଲ"],
        "VILLAGE": ["ମୌଜା", "ଗ୍ରାମ"],
        "RECORD_YEAR": ["ବର୍ଷ"],
        "KHATA": ["ଖାତା ନଂ", "ଖାତା"],
        "KHASRA": ["ପ୍ଲଟ ନଂ", "ପ୍ଲଟ"],
        "AREA": ["ରକବା", "କ୍ଷେତ୍ରଫଳ"],
        "LAND_CLASS": ["କିସମ"],
        "MUTATION": ["ମ୍ୟୁଟେସନ ନଂ"],
        "DATE": ["ତାରିଖ"],
        "GUARDIAN": ["ପିତା / ସ୍ୱାମୀ", "ପିତା", "ସ୍ୱାମୀ"],
    },
    "ml": {
        "DISTRICT": ["ജില്ല"],
        "TEHSIL": ["താലൂക്ക്"],
        "VILLAGE": ["വില്ലേജ്", "ഗ്രാമം"],
        "RECORD_YEAR": ["വർഷം"],
        "KHATA": ["തണ്ടപ്പേര് നമ്പർ", "തണ്ടപ്പേര്"],
        "KHASRA": ["സർവ്വേ നമ്പർ", "സർവേ നമ്പർ", "റീസർവ്വേ നമ്പർ"],
        "AREA": ["വിസ്തീർണ്ണം"],
        "LAND_CLASS": ["ഭൂമിയുടെ തരം"],
        "MUTATION": ["പോക്കുവരവ് നമ്പർ"],
        "DATE": ["തീയതി"],
        "GUARDIAN": ["പിതാവ് / ഭർത്താവ്", "പിതാവ്", "ഭർത്താവ്"],
    },
}

#: Column headings that introduce a table of owners.
OWNER_COLUMN_LABELS_BY_LANGUAGE: dict[str, list[str]] = {
    "hi": ["खातेदार का नाम", "नाम", "नवीन खातेदार"],
    "te": ["పట్టాదారు పేరు", "పట్టాదారుని పేరు", "పేరు"],
    "ta": ["உரிமையாளர் பெயர்", "பட்டாதாரர் பெயர்", "பெயர்"],
    "kn": ["ಖಾತೆದಾರರ ಹೆಸರು", "ಮಾಲೀಕರ ಹೆಸರು", "ಹೆಸರು"],
    "bn": ["রায়তের নাম", "মালিকের নাম", "নাম"],
    "gu": ["ખાતેદારનું નામ", "કબજેદારનું નામ", "નામ"],
    "pa": ["ਮਾਲਕ ਦਾ ਨਾਮ", "ਨਾਮ"],
    "or": ["ରୟତଙ୍କ ନାମ", "ନାମ"],
    "ml": ["ഉടമയുടെ പേര്", "പേര്"],
}

SHARE_COLUMN_LABELS_BY_LANGUAGE: dict[str, list[str]] = {
    "hi": ["अंश"],
    "te": ["వాటా"],
    "ta": ["பங்கு"],
    "kn": ["ಪಾಲು"],
    "bn": ["অংশ"],
    "gu": ["હિસ્સો"],
    "pa": ["ਹਿੱਸਾ"],
    "or": ["ଅଂଶ"],
    "ml": ["ഓഹരി"],
}

GUARDIAN_COLUMN_LABELS_BY_LANGUAGE: dict[str, list[str]] = {
    "hi": ["पिता / पति"],
    "te": ["తండ్రి / భర్త"],
    "ta": ["தந்தை / கணவர்"],
    "kn": ["ತಂದೆ / ಗಂಡ"],
    "bn": ["পিতা / স্বামী"],
    "gu": ["પિતા / પતિ"],
    "pa": ["ਪਿਤਾ / ਪਤੀ"],
    "or": ["ପିତା / ସ୍ୱାମୀ"],
    "ml": ["പിതാവ് / ഭർത്താവ്"],
}

#: Blocks that are page furniture -- state names, form titles, signature and
#: seal captions -- and never a field value.
CHROME_BY_LANGUAGE: dict[str, set[str]] = {
    "hi": {
        "उत्तर प्रदेश", "खसरा", "खतौनी", "नामांतरण पंजिका", "भूमि विवरण",
        "खातेदारों का विवरण", "प्रमाणित किया जाता है", "हस्ताक्षर / लेखपाल",
        "डेमो", "मुहर", "क्र.", "टिप्पणी", "प्रकार",
    },
    "te": {
        "తెలంగాణ", "ఆంధ్ర ప్రదేశ్", "పహాణి", "అడంగల్", "సంతకం", "ముద్ర",
        "క్ర.సం", "గమనిక",
    },
    "ta": {
        "தமிழ்நாடு", "சிட்டா", "அடங்கல்", "கையொப்பம்", "முத்திரை",
        "வ.எண்", "குறிப்பு",
    },
    "kn": {
        "ಕರ್ನಾಟಕ", "ಪಹಣಿ", "ಆರ್.ಟಿ.ಸಿ", "ಸಹಿ", "ಮುದ್ರೆ", "ಕ್ರ.ಸಂ", "ಷರಾ",
    },
    "bn": {"পশ্চিমবঙ্গ", "পরচা", "স্বাক্ষর", "সীলমোহর", "মন্তব্য"},
    "gu": {"ગુજરાત", "સહી", "સિક્કો", "નોંધ"},
    "pa": {"ਪੰਜਾਬ", "ਜਮ੍ਹਾਬੰਦੀ", "ਦਸਤਖ਼ਤ", "ਮੋਹਰ", "ਕੈਫੀਅਤ"},
    "or": {"ଓଡ଼ିଶା", "ସ୍ୱାକ୍ଷର", "ମୋହର", "ମନ୍ତବ୍ୟ"},
    "ml": {"കേരളം", "ഒപ്പ്", "മുദ്ര", "കുറിപ്പ്"},
}

#: Words that open the line after the owners table -- the remark or the
#: certification footer. The table stops there.
TABLE_TERMINATORS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    "hi": ("टिप्पणी", "प्रमाणित"),
    "te": ("గమనిక", "ధృవీకరించడమైనది"),
    "ta": ("குறிப்பு", "சான்றளிக்கப்படுகிறது"),
    "kn": ("ಷರಾ", "ಟಿಪ್ಪಣಿ", "ದೃಢೀಕರಿಸಲಾಗಿದೆ"),
    "bn": ("মন্তব্য", "প্রত্যয়িত"),
    "gu": ("નોંધ", "પ્રમાણિત"),
    "pa": ("ਕੈਫੀਅਤ", "ਤਸਦੀਕ"),
    "or": ("ମନ୍ତବ୍ୟ", "ପ୍ରମାଣିତ"),
    "ml": ("കുറിപ്പ്", "സാക്ഷ്യപ്പെടുത്തുന്നു"),
}

LANGUAGES: tuple[str, ...] = tuple(LABELS_BY_LANGUAGE)


def _merge_fields(by_language: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for fields in by_language.values():
        for name, variants in fields.items():
            merged.setdefault(name, []).extend(variants)
    return merged


def _merge_lists(by_language: dict[str, list[str]]) -> list[str]:
    return [label for labels in by_language.values() for label in labels]


LABELS: dict[str, list[str]] = _merge_fields(LABELS_BY_LANGUAGE)
OWNER_COLUMN_LABELS: list[str] = _merge_lists(OWNER_COLUMN_LABELS_BY_LANGUAGE)
SHARE_COLUMN_LABELS: list[str] = _merge_lists(SHARE_COLUMN_LABELS_BY_LANGUAGE)
GUARDIAN_COLUMN_LABELS: list[str] = _merge_lists(GUARDIAN_COLUMN_LABELS_BY_LANGUAGE)
CHROME: set[str] = set().union(*CHROME_BY_LANGUAGE.values())
TABLE_TERMINATORS: tuple[str, ...] = tuple(
    term for terms in TABLE_TERMINATORS_BY_LANGUAGE.values() for term in terms
)

__all__ = [
    "CHROME", "CHROME_BY_LANGUAGE", "GUARDIAN_COLUMN_LABELS",
    "GUARDIAN_COLUMN_LABELS_BY_LANGUAGE", "LABELS", "LABELS_BY_LANGUAGE",
    "LANGUAGES", "OWNER_COLUMN_LABELS", "OWNER_COLUMN_LABELS_BY_LANGUAGE",
    "SHARE_COLUMN_LABELS", "SHARE_COLUMN_LABELS_BY_LANGUAGE", "TABLE_TERMINATORS",
    "TABLE_TERMINATORS_BY_LANGUAGE",
]
