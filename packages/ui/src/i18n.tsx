"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { cn } from "./cn";
import { en, type MessageKey } from "./messages/en";
import { hi } from "./messages/hi";

/**
 * The language the INTERFACE speaks.
 *
 * Deliberately separate from `DisplayLanguage` in record-text.tsx, which
 * governs how a record VALUE is shown. The two answer different questions and
 * must be able to disagree: a citizen reading a Hindi interface is often
 * reading a record whose owner names they want transliterated, and a verifier
 * working in English must still see the Devanagari exactly as scanned.
 *
 * Nothing here ever touches record data. Interface strings come from a
 * catalogue; record values come from the API and are rendered as written (§44).
 */

export type UiLanguage = "en" | "hi";

const CATALOGUES: Record<UiLanguage, Record<MessageKey, string>> = { en, hi };

const STORAGE_KEY = "mrittika.uiLanguage";

type UiLanguageValue = {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  t: (key: MessageKey) => string;
};

const UiLanguageContext = createContext<UiLanguageValue>({
  language: "en",
  setLanguage: () => {},
  t: (key) => en[key] ?? key,
});

export function UiLanguageProvider({
  defaultLanguage = "en",
  children,
}: {
  /**
   * What this role reads by default. Citizens default to Hindi because the
   * records are in Hindi and the portal is public-facing; officers default to
   * English because the revenue service's working language is English and
   * every internal screen, export and audit entry is already in it.
   *
   * A stored choice always wins -- the default is a starting point, not a
   * policy about what someone can read.
   */
  defaultLanguage?: UiLanguage;
  children: ReactNode;
}) {
  const [language, setLanguageState] = useState<UiLanguage>(defaultLanguage);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "en" || stored === "hi") setLanguageState(stored);
    } catch {
      // Storage can be unavailable (private mode, blocked site data). The
      // default still renders; the choice just is not remembered.
    }
  }, []);

  useEffect(() => {
    // Assistive technology and the browser both need to know what language the
    // page is in; a Hindi interface announced as English is read out wrong.
    if (typeof document !== "undefined") {
      document.documentElement.lang = language;
    }
  }, [language]);

  const setLanguage = useCallback((next: UiLanguage) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // See above.
    }
  }, []);

  const value = useMemo<UiLanguageValue>(() => {
    const catalogue = CATALOGUES[language];
    return {
      language,
      setLanguage,
      // Falls back to English rather than rendering a raw key. A missing
      // string should read as untranslated, never as "citizen.nav.myLand".
      t: (key: MessageKey) => catalogue[key] ?? en[key] ?? key,
    };
  }, [language, setLanguage]);

  return (
    <UiLanguageContext.Provider value={value}>{children}</UiLanguageContext.Provider>
  );
}

export function useUiLanguage() {
  return useContext(UiLanguageContext);
}

/** `const t = useT(); t("citizen.nav.myLand")` */
export function useT() {
  return useContext(UiLanguageContext).t;
}

export function UiLanguageToggle({ className }: { className?: string }) {
  const { language, setLanguage, t } = useUiLanguage();

  return (
    <div
      className={cn("inline-flex items-center rounded-md border border-border", className)}
      role="group"
      aria-label={t("lang.label")}
    >
      {(["en", "hi"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => setLanguage(option)}
          aria-pressed={language === option}
          // Both the visible text and the ACCESSIBLE NAME come from the
          // target language's catalogue, never the current one. Labelling the
          // "switch to English" control in Hindi leaves it unreachable to a
          // screen-reader user who cannot read Hindi -- precisely the person
          // the control exists for.
          aria-label={
            option === "hi" ? hi["lang.switchToHindi"] : en["lang.switchToEnglish"]
          }
          className={cn(
            "px-2 py-1 text-xs font-medium transition-colors first:rounded-l-md last:rounded-r-md",
            language === option
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option === "hi" ? hi["lang.hindi"] : en["lang.english"]}
        </button>
      ))}
    </div>
  );
}

export { en, hi };
export type { MessageKey };
