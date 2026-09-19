/**
 * Hindi UI strings.
 *
 * Typed as `typeof en`, deliberately. A key added to en.ts and forgotten here
 * is a compile error in `tsc --noEmit`, which already runs in CI -- so key
 * parity cannot drift, and there is no separate lint rule to remember.
 *
 * Translation notes:
 *
 *  * Revenue vocabulary stays in its own words. खसरा, खाता, तहसील and ग्राम are
 *    what the documents say and what an officer says out loud; translating
 *    them into "plot number" and back would make the interface disagree with
 *    the paper it describes.
 *  * The language names are each written in their OWN language -- "English"
 *    and "हिन्दी" -- in both catalogues, because a language switcher that
 *    labels the option you cannot read in the language you cannot read is
 *    useless to the person who needs it.
 */

import type { MessageKey } from "./en";

// Record<MessageKey, string>, not `typeof en`: en.ts is `as const`, so
// `typeof en` demands the same literal STRINGS, not the same keys -- every
// translation would be a type error. This form enforces exactly what matters:
// a missing key fails, and an extra key fails as an excess property.
export const hi: Record<MessageKey, string> = {
  // --- chrome ---------------------------------------------------------
  "app.name": "मृत्तिका AI",
  "app.tagline": "भारत के भू-अभिलेखों का बुद्धिमान डिजिटलीकरण",
  "app.synthetic": "नमूना डेटा — वास्तविक भू-अभिलेख नहीं",
  "nav.signOut": "साइन आउट",
  "nav.signedInAs": "साइन इन:",
  "lang.label": "भाषा",
  "lang.english": "English",
  "lang.hindi": "हिन्दी",
  "lang.switchToHindi": "इंटरफ़ेस हिन्दी में बदलें",
  "lang.switchToEnglish": "इंटरफ़ेस अंग्रेज़ी में बदलें",

  // --- roles ----------------------------------------------------------
  "role.citizen": "नागरिक",
  "role.deo": "डेटा एंट्री ऑपरेटर",
  "role.verifier": "सत्यापनकर्ता",
  "role.tehsildar": "तहसीलदार",

  // --- login ----------------------------------------------------------
  "login.title": "साइन इन करें",
  "login.email": "ईमेल",
  "login.password": "पासवर्ड",
  "login.submit": "साइन इन करें",
  "login.working": "साइन इन हो रहा है…",
  "login.failed": "ये विवरण स्वीकार नहीं किए गए।",

  // --- common states --------------------------------------------------
  "state.loading": "लोड हो रहा है…",
  "state.empty": "अभी दिखाने के लिए कुछ नहीं",
  "state.error": "कुछ गलत हो गया",
  "state.retry": "पुनः प्रयास करें",
  "state.forbidden": "इस स्क्रीन तक आपकी पहुँच नहीं है",
  "action.search": "खोजें",
  "action.close": "बंद करें",
  "action.back": "वापस",
  "action.viewDetails": "विवरण देखें",

  // --- citizen navigation ---------------------------------------------
  "citizen.nav.dashboard": "सारांश",
  "citizen.nav.myLand": "मेरी भूमि",
  "citizen.nav.search": "अभिलेख खोजें",
  "citizen.nav.map": "मानचित्र",
  "citizen.nav.grievances": "शिकायतें",
  "citizen.nav.assistant": "सहायक",
  "citizen.section.title": "नागरिक पोर्टल",

  // --- citizen: my land -----------------------------------------------
  "citizen.myLand.title": "मेरी भूमि",
  "citizen.myLand.subtitle": "आपके नाम दर्ज भूखंड",
  "citizen.myLand.empty": "अभी आपके नाम कोई भूखंड दर्ज नहीं है",
  "citizen.myLand.area": "क्षेत्रफल",
  "citizen.myLand.khasra": "खसरा संख्या",
  "citizen.myLand.village": "ग्राम",
  "citizen.myLand.landClass": "भूमि श्रेणी",

  // --- citizen: search -------------------------------------------------
  "citizen.search.title": "अभिलेख खोजें",
  "citizen.search.subtitle": "केवल स्वीकृत अभिलेख",
  "citizen.search.placeholder": "खसरा संख्या, खाता संख्या या ग्राम",
  "citizen.search.empty": "इस खोज से कोई स्वीकृत अभिलेख नहीं मिला",
  "citizen.search.results": "परिणाम",

  // --- citizen: grievances ---------------------------------------------
  "citizen.grievances.title": "शिकायतें",
  "citizen.grievances.subtitle": "आपके द्वारा उठाए गए मुद्दे",
  "citizen.grievances.empty": "आपने कोई शिकायत दर्ज नहीं की है",
  "citizen.grievances.file": "शिकायत दर्ज करें",
  "citizen.grievances.issueType": "मुद्दा",
  "citizen.grievances.submit": "जमा करें",
  "citizen.grievances.filed": "आपकी शिकायत दर्ज कर ली गई है",

  // --- citizen: map ----------------------------------------------------
  "citizen.map.title": "मानचित्र",
  "citizen.map.subtitle": "आपके ग्राम में भूखंड की सीमाएँ",

  // --- citizen: assistant ----------------------------------------------
  "citizen.assistant.title": "सहायक",
  "citizen.assistant.subtitle": "उत्तर केवल स्वीकृत अभिलेखों से लिए जाते हैं",
  "citizen.assistant.placeholder": "अपने भू-अभिलेखों के बारे में पूछें",
  "citizen.assistant.send": "पूछें",
  "citizen.assistant.thinking": "आपके अभिलेख देखे जा रहे हैं…",
  "citizen.assistant.grounding": "हर उत्तर उस अभिलेख का हवाला देता है जिससे वह आया है।",

  "citizen.myLand.description": "आपकी स्वामी पहचान से जुड़े भूखंड। यह आपके सत्र से लिया गया है, इस पृष्ठ द्वारा भेजी गई किसी जानकारी से नहीं।",
  "citizen.myLand.viewLabel": "दृश्य",
  "citizen.myLand.cards": "कार्ड",
  "citizen.myLand.table": "तालिका",
  "citizen.myLand.emptyTitle": "अभी आपके नाम कुछ भी दर्ज नहीं है",
  "citizen.myLand.emptyBody": "जब तहसीलदार किसी अभिलेख को स्वीकृत करते हैं जिसमें आप धारक हैं, तब भूखंड यहाँ दिखाई देंगे।",
  "citizen.myLand.searchPublic": "सार्वजनिक अभिलेख खोजें",
  "citizen.myLand.openRecord": "अभिलेख खोलें",
  "citizen.myLand.map": "मानचित्र",
  "citizen.myLand.parcel": "भूखंड",
  "citizen.myLand.share": "हिस्सा",
  "citizen.myLand.heldSince": "से धारित",
  "citizen.myLand.record": "अभिलेख",
  "citizen.myLand.loadLabel": "आपके भूखंड",
  "citizen.search.description": "स्वीकृत सार्वजनिक भू-अभिलेख। स्थान, खसरा, खाता या भूखंड पहचानकर्ता से खोजें।",
  "citizen.search.khasraLabel": "खसरा संख्या",
  "citizen.search.khataLabel": "खाता संख्या",
  "citizen.search.parcelLabel": "भूखंड पहचानकर्ता",
  "citizen.search.villageLabel": "ग्राम",
  "citizen.search.resultsTitle": "परिणाम",
  "citizen.search.loadLabel": "खोज परिणाम",
  "citizen.search.emptyTitle": "इन फ़िल्टरों से कोई स्वीकृत अभिलेख नहीं मिला",
  "citizen.search.emptyBody": "व्यापक खोज करें — केवल ग्राम, या केवल खसरा संख्या।",
  "citizen.grievances.description": "किसी अभिलेख से जुड़ी समस्या दर्ज करें और उसकी प्रगति देखें।",
  "citizen.grievances.raiseTitle": "शिकायत दर्ज करें",
  "citizen.grievances.whichParcel": "कौन सा भूखंड?",
  "citizen.grievances.whatIsWrong": "क्या गलत है?",
  "citizen.grievances.describe": "समस्या का विवरण दें",
  "citizen.grievances.attachment": "समर्थक दस्तावेज़",
  "citizen.grievances.yoursTitle": "आपकी शिकायतें",
  "citizen.grievances.loadLabel": "आपकी शिकायतें",
  "citizen.grievances.emptyTitle": "आपने अभी कुछ दर्ज नहीं किया है",
  "citizen.grievances.emptyBody": "यदि आपकी भूमि का कोई अभिलेख गलत लगे, तो बाईं ओर दर्ज करें; कोई अधिकारी उसकी समीक्षा करेगा।",
  "citizen.assistant.heading": "अपने अभिलेखों के बारे में पूछें",
  "citizen.assistant.description": "सहायक केवल उन्हीं अभिलेखों तक पहुँच सकता है जिन्हें देखने का आपको पहले से अधिकार है, और वह अपने स्रोत का हवाला देता है।",
  "citizen.assistant.loadLabel": "सहायक",
  "citizen.dashboard.description": "तहसीलदार द्वारा स्वीकृत, आपके नाम दर्ज सब कुछ।",
  "citizen.dashboard.loadLabel": "आपका सारांश",
  "citizen.dashboard.myParcels": "मेरे भूखंड",
  "citizen.dashboard.totalArea": "कुल दर्ज क्षेत्रफल",
  "citizen.dashboard.verifiedRecords": "सत्यापित अभिलेख",
  "citizen.dashboard.openGrievances": "लंबित शिकायतें",
  "citizen.dashboard.recordsTitle": "मेरे भू-अभिलेख",
  "citizen.dashboard.recordsBody": "हर पंक्ति एक भूखंड है जिसमें आपका हित है।",
  "citizen.dashboard.emptyTitle": "अभी आपके नाम कोई भूखंड दर्ज नहीं है",
  "citizen.dashboard.emptyBody": "जब तहसीलदार किसी अभिलेख को स्वीकृत करते हैं जिसमें आप धारक हैं, तब भूखंड यहाँ दिखाई देगा।",
  "citizen.map.loadLabel": "मानचित्र",
  "citizen.map.heading": "भूखंड मानचित्र",
  "citizen.map.description": "आपके भूखंड नारंगी रंग में भरे हैं; शेष ग्राम संदर्भ के लिए दिखाया गया है।",
  "citizen.map.emptyTitle": "दिखाने के लिए कोई भूखंड नहीं",
  "citizen.map.emptyBody": "जब आपके नाम वाला अभिलेख स्वीकृत हो जाएगा, उसका भूखंड यहाँ दिखाई देगा।",
  "citizen.map.cadastreLabel": "भू-मानचित्र",
  "citizen.map.cadastreErrorTitle": "भू-मानचित्र लोड नहीं हो सका",
  "citizen.map.cadastreErrorBody": "इस ग्राम की भूखंड ज्यामिति इस समय उपलब्ध नहीं है।",
  "citizen.map.closePanel": "पैनल बंद करें",
  "citizen.map.historyLabel": "इतिहास",
  // --- officer navigation ----------------------------------------------
  "deo.section.title": "डेटा प्रविष्टि",
  "deo.nav.dashboard": "डैशबोर्ड",
  "deo.nav.upload": "अपलोड",
  "verifier.section.title": "सत्यापन",
  "verifier.nav.dashboard": "डैशबोर्ड",
  "verifier.nav.queue": "कतार",
  "tehsildar.section.title": "तहसीलदार",
  "tehsildar.nav.dashboard": "डैशबोर्ड",
  "tehsildar.nav.approvals": "अनुमोदन",
  "tehsildar.nav.analytics": "विश्लेषण",
  "tehsildar.nav.map": "मानचित्र",
  "tehsildar.nav.grievances": "शिकायतें",
  "tehsildar.nav.assistant": "सहायक",
  "oversight.section.title": "निगरानी",
  "oversight.nav.analytics": "विश्लेषण",
  "oversight.nav.map": "मानचित्र",
  "oversight.nav.research": "शोध डेटा",

  "record.title": "अभिलेख",

  "deo.nav.bulk": "बैच अपलोड",

  // --- record presentation ----------------------------------------------
  "record.asWritten": "जैसा लिखा है",
  "record.english": "अंग्रेज़ी पाठ",
  "record.transliterated": "लिप्यंतरण, अनुवाद नहीं",
};
