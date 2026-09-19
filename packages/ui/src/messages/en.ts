/**
 * English UI strings.
 *
 * This file is the source of truth for the KEY SET. `hi.ts` declares itself as
 * `typeof en`, so a key added here and forgotten there fails `tsc --noEmit` --
 * which already runs in CI. Key parity is a type error, not a lint rule
 * somebody can skip.
 *
 * What belongs here: chrome. Navigation, buttons, headings, empty states,
 * errors -- words the application says.
 *
 * What must NEVER be here: anything read off a record. A village name, an
 * owner, a khasra number and an area are data, not interface. They render
 * through RecordText, which shows the original and can show a transliteration
 * beside it, and they are never looked up in a message catalogue (§44).
 */

export const en = {
  // --- chrome ---------------------------------------------------------
  "app.name": "Mrittika AI",
  "app.tagline": "Intelligent digitization for India's land records",
  "app.synthetic": "Demo data — no real land record",
  "nav.signOut": "Sign out",
  "nav.signedInAs": "Signed in as",
  "lang.label": "Language",
  "lang.english": "English",
  "lang.hindi": "हिन्दी",
  "lang.switchToHindi": "Switch interface to Hindi",
  "lang.switchToEnglish": "Switch interface to English",

  // --- roles ----------------------------------------------------------
  "role.citizen": "Citizen",
  "role.deo": "Data Entry Operator",
  "role.verifier": "Verifier",
  "role.tehsildar": "Tehsildar",

  // --- login ----------------------------------------------------------
  "login.title": "Sign in",
  "login.email": "Email",
  "login.password": "Password",
  "login.submit": "Sign in",
  "login.working": "Signing in…",
  "login.failed": "Those credentials were not accepted.",

  // --- common states --------------------------------------------------
  "state.loading": "Loading…",
  "state.empty": "Nothing to show yet",
  "state.error": "Something went wrong",
  "state.retry": "Try again",
  "state.forbidden": "You do not have access to this screen",
  "action.search": "Search",
  "action.close": "Close",
  "action.back": "Back",
  "action.viewDetails": "View details",

  // --- citizen navigation ---------------------------------------------
  "citizen.nav.dashboard": "Overview",
  "citizen.nav.myLand": "My land",
  "citizen.nav.search": "Search records",
  "citizen.nav.map": "Map",
  "citizen.nav.grievances": "Grievances",
  "citizen.nav.assistant": "Assistant",
  "citizen.section.title": "Citizen portal",

  // --- citizen: my land -----------------------------------------------
  "citizen.myLand.title": "My land",
  "citizen.myLand.subtitle": "Parcels recorded in your name",
  "citizen.myLand.empty": "No parcels are recorded in your name yet",
  "citizen.myLand.area": "Area",
  "citizen.myLand.khasra": "Khasra number",
  "citizen.myLand.village": "Village",
  "citizen.myLand.landClass": "Land class",

  // --- citizen: search -------------------------------------------------
  "citizen.search.title": "Search records",
  "citizen.search.subtitle": "Approved records only",
  "citizen.search.placeholder": "Khasra number, khata number or village",
  "citizen.search.empty": "No approved records matched that search",
  "citizen.search.results": "Results",

  // --- citizen: grievances ---------------------------------------------
  "citizen.grievances.title": "Grievances",
  "citizen.grievances.subtitle": "Issues you have raised",
  "citizen.grievances.empty": "You have not raised any grievances",
  "citizen.grievances.file": "Raise a grievance",
  "citizen.grievances.issueType": "Issue",
  "citizen.grievances.submit": "Submit",
  "citizen.grievances.filed": "Your grievance was recorded",

  // --- citizen: map ----------------------------------------------------
  "citizen.map.title": "Map",
  "citizen.map.subtitle": "Parcel boundaries in your village",

  // --- citizen: assistant ----------------------------------------------
  "citizen.assistant.title": "Assistant",
  "citizen.assistant.subtitle": "Answers drawn only from approved records",
  "citizen.assistant.placeholder": "Ask about your land records",
  "citizen.assistant.send": "Ask",
  "citizen.assistant.thinking": "Looking through your records…",
  "citizen.assistant.grounding": "Every answer cites the record it came from.",

  "citizen.myLand.description": "Parcels linked to your owner identity. Derived from your session, not from anything this page sends.",
  "citizen.myLand.viewLabel": "View",
  "citizen.myLand.cards": "Cards",
  "citizen.myLand.table": "Table",
  "citizen.myLand.emptyTitle": "Nothing is recorded against your name yet",
  "citizen.myLand.emptyBody": "Parcels appear here once a tehsildar approves a record naming you as a holder.",
  "citizen.myLand.searchPublic": "Search public records",
  "citizen.myLand.openRecord": "Open record",
  "citizen.myLand.map": "Map",
  "citizen.myLand.parcel": "Parcel",
  "citizen.myLand.share": "Share",
  "citizen.myLand.heldSince": "Held since",
  "citizen.myLand.record": "Record",
  "citizen.myLand.loadLabel": "your parcels",
  "citizen.search.description": "Approved public land records. Search by location, khasra, khata or parcel identifier.",
  "citizen.search.khasraLabel": "Khasra number",
  "citizen.search.khataLabel": "Khata number",
  "citizen.search.parcelLabel": "Parcel identifier",
  "citizen.search.villageLabel": "Village",
  "citizen.search.resultsTitle": "Results",
  "citizen.search.loadLabel": "search results",
  "citizen.search.emptyTitle": "No approved records match those filters",
  "citizen.search.emptyBody": "Try a broader search — a village on its own, or just the khasra number.",
  "citizen.grievances.description": "Raise an issue with a record, and follow what happens to it.",
  "citizen.grievances.raiseTitle": "Raise a grievance",
  "citizen.grievances.whichParcel": "Which parcel?",
  "citizen.grievances.whatIsWrong": "What is wrong?",
  "citizen.grievances.describe": "Describe the problem",
  "citizen.grievances.attachment": "Supporting document",
  "citizen.grievances.yoursTitle": "Your grievances",
  "citizen.grievances.loadLabel": "your grievances",
  "citizen.grievances.emptyTitle": "You have not raised anything yet",
  "citizen.grievances.emptyBody": "If a record about your land looks wrong, file it on the left and an officer will review it.",
  "citizen.assistant.heading": "Ask about your records",
  "citizen.assistant.description": "The assistant can only reach records you are already entitled to see, and cites what it used.",
  "citizen.assistant.loadLabel": "the assistant",
  "citizen.dashboard.description": "Everything recorded against your name, as approved by the tehsildar.",
  "citizen.dashboard.loadLabel": "your summary",
  "citizen.dashboard.myParcels": "My parcels",
  "citizen.dashboard.totalArea": "Total recorded area",
  "citizen.dashboard.verifiedRecords": "Verified records",
  "citizen.dashboard.openGrievances": "Open grievances",
  "citizen.dashboard.recordsTitle": "My land records",
  "citizen.dashboard.recordsBody": "Each row is a parcel you hold an interest in.",
  "citizen.dashboard.emptyTitle": "No parcels are recorded against your name yet",
  "citizen.dashboard.emptyBody": "A parcel appears here once a tehsildar approves a record naming you as a holder.",
  "citizen.map.loadLabel": "the map",
  "citizen.map.heading": "Parcel map",
  "citizen.map.description": "Your parcels are filled in orange; the rest of the village is drawn for context.",
  "citizen.map.emptyTitle": "No parcels to show",
  "citizen.map.emptyBody": "Once a record naming you is approved, its parcel appears here.",
  "citizen.map.cadastreLabel": "the cadastre",
  "citizen.map.cadastreErrorTitle": "The cadastre could not be loaded",
  "citizen.map.cadastreErrorBody": "The parcel geometry for this village is unavailable right now.",
  "citizen.map.closePanel": "Close panel",
  "citizen.map.historyLabel": "the history",
  // --- officer navigation ----------------------------------------------
  "deo.section.title": "Data entry",
  "deo.nav.dashboard": "Dashboard",
  "deo.nav.upload": "Upload",
  "verifier.section.title": "Verification",
  "verifier.nav.dashboard": "Dashboard",
  "verifier.nav.queue": "Queue",
  "tehsildar.section.title": "Tehsildar",
  "tehsildar.nav.dashboard": "Dashboard",
  "tehsildar.nav.approvals": "Approvals",
  "tehsildar.nav.analytics": "Analytics",
  "tehsildar.nav.map": "Map",
  "tehsildar.nav.grievances": "Grievances",
  "tehsildar.nav.assistant": "Assistant",
  "oversight.section.title": "Oversight",
  "oversight.nav.analytics": "Analytics",
  "oversight.nav.map": "Map",
  "oversight.nav.research": "Research data",

  "record.title": "Record",

  "deo.nav.bulk": "Batch upload",

  // --- record presentation ----------------------------------------------
  // These label record values; they never translate them.
  "record.asWritten": "As written",
  "record.english": "English reading",
  "record.transliterated": "Transliterated, not translated",
} as const;

export type MessageKey = keyof typeof en;
