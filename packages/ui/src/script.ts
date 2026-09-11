/**
 * Reading Hindi record values in English.
 *
 * Deterministic on purpose. A language model would read these values more
 * fluently, and would also invent spellings for people's names -- §82 forbids
 * fabricated record output, and a verifier comparing against a Hindi scan needs
 * to know exactly where the English came from. So every result says how it was
 * produced:
 *
 *   glossary         a fixed translation of a known record term
 *                    (सिंचित -> Irrigated, बीघा -> bigha), or an official place
 *                    name supplied from the locations table (रामपुर -> Rampur)
 *   transliteration  a rule-based romanisation (गिरधारी देवी -> Girdhari Devi);
 *                    readable, but not necessarily how the person spells it
 *   mixed            some of each
 *   none             nothing to convert (ASCII, digits, empty)
 *
 * The original is never discarded -- callers show it beside the English.
 */

export type EnglishMethod = "glossary" | "transliteration" | "mixed" | "none";

export type EnglishReading = {
  english: string;
  method: EnglishMethod;
  /** True when the input contained any Devanagari at all. */
  hasDevanagari: boolean;
};

/** Record vocabulary that appears as VALUES on the documents. */
export const RECORD_GLOSSARY: Record<string, string> = {
  // Land classification (§43)
  सिंचित: "Irrigated",
  असिंचित: "Unirrigated",
  बंजर: "Barren",
  चारागाह: "Pasture",
  आबादी: "Habitation",
  // Area units
  बीघा: "bigha",
  बिस्वा: "biswa",
  हेक्टेयर: "hectare",
  एकड़: "acre",
  // Mutation types
  विक्रय: "Sale",
  उत्तराधिकार: "Inheritance",
  दान: "Gift",
  बंटवारा: "Partition",
  "न्यायालय आदेश": "Court decree",
  शुद्धि: "Correction",
  अन्य: "Other",
  // Administrative units
  "उत्तर प्रदेश": "Uttar Pradesh",
  "डेमो जिला": "Demo District",
  "डेमो तहसील": "Demo Tehsil",
  जिला: "District",
  तहसील: "Tehsil",
  ग्राम: "Village",
  // Remarks and prefixes
  टिप्पणी: "Remark",
  "अभिलेख डिजिटलीकरण हेतु": "For record digitisation",
  "स्व.": "Late",
};

const DEVANAGARI = /[ऀ-ॿ]/;

const INDEPENDENT_VOWELS: Record<string, string> = {
  अ: "a", आ: "a", इ: "i", ई: "i", उ: "u", ऊ: "u", ऋ: "ri",
  ए: "e", ऐ: "ai", ओ: "o", औ: "au",
};

/** Dependent vowel signs. ई is resolved by position: 'ee' inside a word, 'i' at the end. */
const MATRAS: Record<string, string> = {
  "ा": "a", "ि": "i", "ी": "ī", "ु": "u", "ू": "u",
  "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
};

const CONSONANTS: Record<string, string> = {
  क: "k", ख: "kh", ग: "g", घ: "gh", ङ: "n",
  च: "ch", छ: "chh", ज: "j", झ: "jh", ञ: "n",
  ट: "t", ठ: "th", ड: "d", ढ: "dh", ण: "n",
  त: "t", थ: "th", द: "d", ध: "dh", न: "n",
  प: "p", फ: "ph", ब: "b", भ: "bh", म: "m",
  य: "y", र: "r", ल: "l", व: "v", श: "sh", ष: "sh", स: "s", ह: "h", ळ: "l",
};

/** Consonant + nukta (U+093C). */
const NUKTA_CONSONANTS: Record<string, string> = {
  ड: "r", ढ: "rh", ज: "z", फ: "f", क: "q", ग: "gh",
};

const HALANT = "्";
const NUKTA = "़";
const ANUSVARA = "ं";
const CHANDRABINDU = "ँ";
const VISARGA = "ः";
const LABIALS = new Set(["p", "ph", "b", "bh", "m"]);

type Unit = {
  consonant: string | null;
  /** '' for halant, 'a' for the inherent vowel, else the matra's value. */
  vowel: string;
  inherent: boolean;
  nasal: "" | "anusvara" | "chandrabindu";
  visarga: boolean;
};

function parseWord(word: string): Unit[] {
  const chars = [...word];
  const units: Unit[] = [];
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    if (CONSONANTS[ch]) {
      let consonant = CONSONANTS[ch];
      if (chars[i + 1] === NUKTA) {
        consonant = NUKTA_CONSONANTS[ch] ?? consonant;
        i++;
      }
      const unit: Unit = { consonant, vowel: "a", inherent: true, nasal: "", visarga: false };
      const next = chars[i + 1];
      if (next === HALANT) {
        unit.vowel = "";
        unit.inherent = false;
        i++;
      } else if (next && MATRAS[next]) {
        unit.vowel = MATRAS[next];
        unit.inherent = false;
        i++;
      }
      units.push(unit);
    } else if (INDEPENDENT_VOWELS[ch]) {
      units.push({
        consonant: null,
        vowel: ch === "ई" ? "ī" : INDEPENDENT_VOWELS[ch],
        inherent: false,
        nasal: "",
        visarga: false,
      });
    } else if (ch === ANUSVARA || ch === CHANDRABINDU) {
      const last = units[units.length - 1];
      if (last) last.nasal = ch === ANUSVARA ? "anusvara" : "chandrabindu";
    } else if (ch === VISARGA) {
      const last = units[units.length - 1];
      if (last) last.visarga = true;
    }
    // Anything else inside a word (avagraha, stray marks) carries no sound.
  }
  return units;
}

/**
 * Hindi drops the inherent 'a' in speech: राम is 'Ram', not 'Rama'; कमला is
 * 'Kamla'. Word-final: dropped unless it closes a consonant cluster (मौर्य ->
 * Maurya). Medial: dropped in V-C(a)-C-V, scanning left to right and never
 * twice in a row (दीनदयाल -> Deendayal, not Deenadyal).
 */
function deleteSchwas(units: Unit[]): void {
  const hasVowel = (u: Unit | undefined) => !!u && u.vowel !== "";
  const last = units.length - 1;

  if (last > 0) {
    const final = units[last];
    const clustered = units[last - 1].vowel === "" && units[last - 1].consonant !== null;
    if (final.inherent && !clustered && !final.nasal) final.vowel = "";
  }

  let skipNext = false;
  for (let i = 1; i < last; i++) {
    if (skipNext) {
      skipNext = false;
      continue;
    }
    const unit = units[i];
    if (!unit.inherent || unit.nasal || unit.visarga) continue;
    const prev = units[i - 1];
    const next = units[i + 1];
    if (hasVowel(prev) && next.consonant !== null && hasVowel(next)) {
      unit.vowel = "";
      skipNext = true;
    }
  }
}

function romaniseWord(word: string): string {
  if (word === "सिंह") return "Singh";
  if (word === "ज्ञान") return "Gyan";

  const units = parseWord(word);
  if (units.length === 0) return word;
  deleteSchwas(units);

  let out = "";
  units.forEach((unit, index) => {
    if (unit.consonant) {
      const prev = units[index - 1];
      // व after a consonant with no vowel of its own reads as 'w':
      // कुशवाहा -> Kushwaha, सोनवर्षा -> Sonwarsha.
      const consonant =
        unit.consonant === "v" && prev && prev.consonant && prev.vowel === "" ? "w" : unit.consonant;
      out += consonant;
    }
    const isLast = index === units.length - 1;
    out += unit.vowel === "ī" ? (isLast ? "i" : "ee") : unit.vowel;
    if (unit.nasal) {
      const following = units[index + 1]?.consonant ?? "";
      out += unit.nasal === "anusvara" && LABIALS.has(following) ? "m" : "n";
    }
    if (unit.visarga) out += "h";
  });
  return out;
}

const DEVANAGARI_DIGITS = "०१२३४५६७८९";

/** Romanise Devanagari text, leaving everything else as it is. */
export function transliterate(text: string): string {
  const normalised = text.normalize("NFC");
  return normalised
    .replace(/[०-९]/g, (d) => String(DEVANAGARI_DIGITS.indexOf(d)))
    .replace(/।/g, ".")
    .replace(/[ऀ-ॿ]+/g, (word) => {
      const roman = romaniseWord(word);
      return roman.charAt(0).toUpperCase() + roman.slice(1);
    });
}

/**
 * An English reading of a record value.
 *
 * `places` maps official Devanagari place names to their English names, from
 * the locations table; they take precedence over the static glossary.
 */
export function toEnglish(
  value: string | null | undefined,
  places: Record<string, string> = {},
): EnglishReading {
  const text = (value ?? "").normalize("NFC").trim();
  if (!text || !DEVANAGARI.test(text)) {
    return { english: text, method: "none", hasDevanagari: false };
  }

  const glossary: Record<string, string> = { ...RECORD_GLOSSARY, ...places };
  const collapse = (s: string) => s.replace(/\s+/g, " ").trim();
  const whole = glossary[collapse(text)];
  if (whole) return { english: whole, method: "glossary", hasDevanagari: true };

  // Longest phrases first, so 'डेमो जिला' wins over 'जिला'.
  const phrases = Object.keys(glossary).sort((a, b) => b.length - a.length);
  let remaining = collapse(text);
  let usedGlossary = false;
  const pieces: string[] = [];

  while (remaining.length) {
    const phrase = phrases.find(
      (p) =>
        remaining.startsWith(p) &&
        (remaining.length === p.length || /[\s:,/()\-]/.test(remaining[p.length]) || p.endsWith(".")),
    );
    if (phrase) {
      pieces.push(glossary[phrase]);
      usedGlossary = true;
      remaining = remaining.slice(phrase.length);
      continue;
    }
    const match = remaining.match(/^(\s+|[^\s]+)/);
    const token = match ? match[0] : remaining;
    pieces.push(token);
    remaining = remaining.slice(token.length);
  }

  const joined = collapse(
    pieces
      .map((piece) => (DEVANAGARI.test(piece) ? transliterate(piece) : piece))
      .join(" ")
      .replace(/\s+([:,.)])/g, "$1"),
  );
  const usedTransliteration = pieces.some((piece) => DEVANAGARI.test(piece));

  return {
    english: joined,
    method: usedGlossary && usedTransliteration ? "mixed" : usedGlossary ? "glossary" : "transliteration",
    hasDevanagari: true,
  };
}
