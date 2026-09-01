import type { ReactNode } from "react";
import {
  ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle,
} from "react-native";

import { colors, radius, spacing } from "../theme";

/** The shared vocabulary, kept small: mobile is capture and consultation only. */

export function Button({
  label,
  onPress,
  variant = "primary",
  busy,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "accent" | "outline" | "ghost";
  busy?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  const inactive = disabled || busy;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy }}
      style={({ pressed }) => [
        styles.button,
        variant === "primary" && { backgroundColor: colors.navy },
        variant === "accent" && { backgroundColor: colors.burnt },
        variant === "outline" && styles.buttonOutline,
        variant === "ghost" && { backgroundColor: "transparent" },
        inactive && { opacity: 0.5 },
        pressed && { opacity: 0.8 },
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator
          size="small"
          color={variant === "outline" || variant === "ghost" ? colors.navy : colors.white}
        />
      ) : null}
      <Text
        style={[
          styles.buttonLabel,
          (variant === "outline" || variant === "ghost") && { color: colors.navy },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <Text style={styles.eyebrow}>{children}</Text>;
}

/** Identifiers are monospaced here too — parcel_id is the spine (§11). */
export function Identifier({ children }: { children: ReactNode }) {
  return <Text style={styles.identifier}>{children}</Text>;
}

export function StatusChip({
  label,
  tone,
}: {
  label: string;
  tone: "neutral" | "progress" | "attention" | "good" | "bad";
}) {
  const palette = {
    neutral: [colors.sand100, colors.sand700],
    progress: [colors.navyLight, colors.navy],
    attention: [colors.mediumBg, colors.medium],
    good: [colors.highBg, colors.high],
    bad: [colors.lowBg, colors.low],
  }[tone];

  return (
    <View style={[styles.chip, { backgroundColor: palette[0] }]}>
      <Text style={[styles.chipLabel, { color: palette[1] }]}>{label}</Text>
    </View>
  );
}

/** §83 — never let a demo look like it holds real citizens' land. */
export function SyntheticNotice() {
  return (
    <View style={styles.synthetic}>
      <Text style={styles.syntheticLabel}>DEMO / SYNTHETIC DATA</Text>
    </View>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      {description ? <Text style={styles.emptyBody}>{description}</Text> : null}
    </View>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <View style={styles.error}>
      <Text style={styles.errorText}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    minHeight: 46,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.card,
  },
  buttonOutline: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.sand200,
  },
  buttonLabel: { color: colors.white, fontSize: 15, fontWeight: "600" },
  card: {
    backgroundColor: colors.white,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.sand200,
    padding: spacing.lg,
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.1,
    textTransform: "uppercase",
    color: colors.sand500,
  },
  identifier: {
    fontFamily: "Menlo",
    fontSize: 12,
    letterSpacing: 0.4,
    color: colors.sand700,
  },
  chip: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.chip,
  },
  chipLabel: { fontSize: 11, fontWeight: "600" },
  synthetic: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.burnt,
    backgroundColor: colors.cream,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.chip,
  },
  syntheticLabel: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
    color: colors.burnt,
  },
  empty: { paddingVertical: spacing.xxl, alignItems: "center", gap: spacing.xs },
  emptyTitle: { fontSize: 15, fontWeight: "600", color: colors.navyDark },
  emptyBody: {
    fontSize: 14,
    color: colors.sand500,
    textAlign: "center",
    paddingHorizontal: spacing.xl,
  },
  error: {
    backgroundColor: colors.lowBg,
    borderRadius: radius.card,
    padding: spacing.md,
  },
  errorText: { color: colors.low, fontSize: 14 },
});
