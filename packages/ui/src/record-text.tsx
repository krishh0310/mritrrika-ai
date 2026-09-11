"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { cn } from "./cn";
import { toEnglish, type EnglishReading } from "./script";

/**
 * How record values are displayed: as written (Hindi), or in English with the
 * Hindi kept beside it.
 *
 * A per-viewer preference, remembered in localStorage. It changes presentation
 * only -- every value sent to the API, and every correction a verifier saves,
 * is the original text.
 */

export type DisplayLanguage = "original" | "english";

const STORAGE_KEY = "mrittika.displayLanguage";

type DisplayLanguageValue = {
  language: DisplayLanguage;
  setLanguage: (language: DisplayLanguage) => void;
  /** Official Devanagari place name -> English name, from the locations table. */
  places: Record<string, string>;
};

const DisplayLanguageContext = createContext<DisplayLanguageValue>({
  language: "original",
  setLanguage: () => {},
  places: {},
});

export function DisplayLanguageProvider({
  places = {},
  children,
}: {
  places?: Record<string, string>;
  children: ReactNode;
}) {
  const [language, setLanguageState] = useState<DisplayLanguage>("english");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "original" || stored === "english") setLanguageState(stored);
    } catch {
      // Storage can be unavailable (private mode, blocked site data). The
      // default still renders correctly; the choice just is not remembered.
    }
  }, []);

  const setLanguage = useCallback((next: DisplayLanguage) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* see above */
    }
  }, []);

  const value = useMemo(() => ({ language, setLanguage, places }), [language, setLanguage, places]);
  return <DisplayLanguageContext.Provider value={value}>{children}</DisplayLanguageContext.Provider>;
}

export function useDisplayLanguage() {
  return useContext(DisplayLanguageContext);
}

/** The English reading of a value under the current preference, or null when showing the original. */
export function useEnglishReading(value: string | null | undefined): EnglishReading | null {
  const { language, places } = useDisplayLanguage();
  return useMemo(
    () => (language === "english" ? toEnglish(value, places) : null),
    [language, places, value],
  );
}

const METHOD_NOTE: Record<string, string> = {
  glossary: "Translated from the record's Hindi",
  transliteration: "Transliterated from Hindi by rule — the spelling may differ from how the name is usually written",
  mixed: "Partly translated, partly transliterated from Hindi — spellings of names may differ",
};

/**
 * One value transcribed from a document.
 *
 * Original mode: the text as written. English mode: the English reading, with
 * the original immediately after it. The original is never hidden, because the
 * page it came from is in Hindi and that is what a reviewer checks against.
 */
export function RecordText({
  value,
  fallback = "—",
  className,
  originalClassName,
  stacked = false,
}: {
  value: string | null | undefined;
  fallback?: ReactNode;
  className?: string;
  /** Styling for the original shown beside the English. */
  originalClassName?: string;
  /** Put the original on its own line (for large values and table cells). */
  stacked?: boolean;
}) {
  const reading = useEnglishReading(value);

  if (!value) return <span className={className}>{fallback}</span>;

  if (!reading || !reading.hasDevanagari) {
    return (
      <span className={cn(isAscii(value) ? undefined : "record-text", className)} lang={isAscii(value) ? undefined : "hi"}>
        {value}
      </span>
    );
  }

  return (
    <span
      className={cn(stacked ? "inline-flex flex-col" : "inline", className)}
      title={METHOD_NOTE[reading.method]}
    >
      <span lang="en">{reading.english}</span>
      <span
        lang="hi"
        className={cn(
          "record-text font-normal text-sand-500",
          stacked ? "text-[0.8125rem] leading-snug" : "ml-1.5 text-[0.9em]",
          originalClassName,
        )}
      >
        {value}
      </span>
    </span>
  );
}

/** A two-way switch for the header. */
export function DisplayLanguageToggle({ className }: { className?: string }) {
  const { language, setLanguage } = useDisplayLanguage();
  const options: { value: DisplayLanguage; label: string; lang?: string }[] = [
    { value: "original", label: "हिन्दी", lang: "hi" },
    { value: "english", label: "English" },
  ];
  return (
    <div
      role="group"
      aria-label="Show record values in"
      className={cn("inline-flex rounded-chip border border-white/20 p-0.5", className)}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          lang={option.lang}
          aria-pressed={language === option.value}
          onClick={() => setLanguage(option.value)}
          className={cn(
            "rounded-[3px] px-2 py-0.5 text-xs font-medium transition-colors",
            language === option.value ? "bg-white text-navy-900" : "text-navy-100 hover:bg-white/10",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Identifiers and numbers get the identifier face; Devanagari must not (its letter-spacing breaks shaping). */
export function isAscii(value: string): boolean {
  return /^[\x20-\x7E]*$/.test(value);
}
