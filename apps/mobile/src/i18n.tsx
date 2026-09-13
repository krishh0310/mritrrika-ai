import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { en, type MessageKey } from "@mrittika/messages/en";
import { hi } from "@mrittika/messages/hi";
import { colors, radius, spacing } from "./theme";

/**
 * The language the interface speaks, on mobile.
 *
 * The catalogues are the SAME files the web app uses -- imported through the
 * @mrittika/messages path, not copied. Two copies of a translation drift, and
 * the drift is invisible until somebody reads the wrong one.
 *
 * The provider is separate from the web one because that one renders DOM
 * elements and reads localStorage synchronously. Here storage is async, so the
 * stored choice arrives one render late; the role default renders first, which
 * is correct rather than merely convenient -- a citizen sees Hindi
 * immediately rather than a flash of English.
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
  defaultLanguage?: UiLanguage;
  children: ReactNode;
}) {
  const [language, setLanguageState] = useState<UiLanguage>(defaultLanguage);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (cancelled) return;
        if (stored === "en" || stored === "hi") setLanguageState(stored);
      })
      .catch(() => {
        // Storage can fail on a locked or full device. The default still
        // renders; the choice just is not remembered.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLanguage = useCallback((next: UiLanguage) => {
    setLanguageState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {});
  }, []);

  const value = useMemo<UiLanguageValue>(() => {
    const catalogue = CATALOGUES[language];
    return {
      language,
      setLanguage,
      // Falls back to English rather than showing a raw key: a missing string
      // should read as untranslated, never as "citizen.nav.myLand".
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

export function useT() {
  return useContext(UiLanguageContext).t;
}

export function UiLanguageToggle() {
  const { language, setLanguage, t } = useUiLanguage();

  return (
    <View style={styles.group} accessibilityRole="radiogroup">
      {(["en", "hi"] as const).map((option) => {
        const active = language === option;
        return (
          <Pressable
            key={option}
            onPress={() => setLanguage(option)}
            accessibilityRole="radio"
            accessibilityState={{ selected: active }}
            accessibilityLabel={
              // Target language, not the current one -- see the web toggle.
              option === "hi" ? hi["lang.switchToHindi"] : en["lang.switchToEnglish"]
            }
            style={[styles.option, active && styles.optionActive]}
          >
            <Text style={[styles.label, active && styles.labelActive]}>
              {option === "hi" ? hi["lang.hindi"] : en["lang.english"]}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: "row",
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.chip,
    overflow: "hidden",
  },
  option: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  optionActive: { backgroundColor: colors.navy },
  label: { fontSize: 12, color: colors.sand700 },
  labelActive: { color: "#fff", fontWeight: "600" },
});

export type { MessageKey };
