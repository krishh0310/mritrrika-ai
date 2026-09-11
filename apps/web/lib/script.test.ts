import { describe, expect, it } from "vitest";

import { toEnglish, transliterate } from "../../../packages/ui/src/script";

/**
 * The name pools the synthetic world is built from, with the spelling a
 * reader would expect. Transliteration is rule-based, so this pins the rules
 * against the vocabulary that actually appears on the documents.
 */
const NAMES: [string, string][] = [
  ["राम प्रसाद सिंह", "Ram Prasad Singh"],
  ["सीमा देवी", "Seema Devi"],
  ["गिरधारी देवी", "Girdhari Devi"],
  ["कैलाश वर्मा", "Kailash Varma"],
  ["श्याम लाल वर्मा", "Shyam Lal Varma"],
  ["हरि शंकर यादव", "Hari Shankar Yadav"],
  ["मोहन", "Mohan"],
  ["कमला", "Kamla"],
  ["राजकुमारी", "Rajkumari"],
  ["दीनदयाल", "Deendayal"],
  ["छोटेलाल गुप्ता", "Chhotelal Gupta"],
  ["रघुनाथ मौर्य", "Raghunath Maurya"],
  ["कुशवाहा", "Kushwaha"],
  ["गीता शर्मा", "Geeta Sharma"],
  ["पुष्पा पाल", "Pushpa Pal"],
  ["ओम प्रकाश", "Om Prakash"],
  ["बाबूराम", "Baburam"],
  ["शांति", "Shanti"],
  ["विद्या", "Vidya"],
  ["उर्मिला", "Urmila"],
];

describe("transliterate", () => {
  it.each(NAMES)("%s -> %s", (hindi, english) => {
    expect(transliterate(hindi)).toBe(english);
  });

  it("converts Devanagari digits and leaves ASCII alone", () => {
    expect(transliterate("१४२/२")).toBe("142/2");
    expect(transliterate("PARCEL-UP-DEMO-0142")).toBe("PARCEL-UP-DEMO-0142");
  });
});

describe("toEnglish", () => {
  it("translates record vocabulary from the glossary", () => {
    expect(toEnglish("सिंचित")).toEqual({ english: "Irrigated", method: "glossary", hasDevanagari: true });
    expect(toEnglish("बीघा").english).toBe("bigha");
    expect(toEnglish("उत्तराधिकार").english).toBe("Inheritance");
    expect(toEnglish("डेमो जिला").english).toBe("Demo District");
  });

  it("prefers official place names over transliteration", () => {
    const places = { मुड़ियाकला: "Mudiyakala" };
    expect(toEnglish("मुड़ियाकला", places)).toMatchObject({ english: "Mudiyakala", method: "glossary" });
  });

  it("says when a name was transliterated rather than translated", () => {
    expect(toEnglish("गिरधारी देवी")).toMatchObject({
      english: "Girdhari Devi",
      method: "transliteration",
    });
  });

  it("combines glossary terms and names", () => {
    expect(toEnglish("स्व. मोहन सिंह")).toMatchObject({ english: "Late Mohan Singh", method: "mixed" });
  });

  it("does nothing to values with no Devanagari", () => {
    expect(toEnglish("2.75")).toEqual({ english: "2.75", method: "none", hasDevanagari: false });
    expect(toEnglish(null).english).toBe("");
  });
});
