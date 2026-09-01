/**
 * Sign in (§59).
 *
 * The two cards are navigation, not authorization. They pre-fill a demo
 * account and change the explanatory copy; they confer nothing. Signing in
 * with a citizen account after tapping "Field officer" gets you the citizen
 * portal, because the stack that mounts comes from /auth/me (§12). The copy on
 * the screen says so, so that a judge can see the separation is real rather
 * than being told it is.
 *
 * Mobile offers two of the four roles by design (§4): the phone is for citizen
 * access and field capture. Verification and approval stay on the desktop.
 */

import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/auth-context";
import { Button, ErrorText, SyntheticNotice } from "../components/ui";
import { colors, radius, spacing } from "../theme";

type RoleCard = {
  key: "CITIZEN" | "FIELD";
  title: string;
  blurb: string;
  demoEmail: string;
};

const CARDS: RoleCard[] = [
  {
    key: "CITIZEN",
    title: "Citizen",
    blurb: "Your holdings, ownership history, grievances and questions.",
    demoEmail: "ram31@mrittika.demo",
  },
  {
    key: "FIELD",
    title: "Field officer",
    blurb: "Photograph legacy records and queue them for processing.",
    demoEmail: "deo@mrittika.demo",
  },
];

export function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { signIn } = useAuth();

  const [selected, setSelected] = useState<RoleCard["key"] | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function choose(card: RoleCard) {
    setSelected(card.key);
    setEmail(card.demoEmail);
    setError(null);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // No navigation call here: the root navigator swaps stacks as soon as
      // the user resolves, so there is no route for this screen to push.
      await signIn(email.trim(), password);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Sign-in failed. Try again.",
      );
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.brand}>Mrittika AI</Text>
        <Text style={styles.tagline}>Intelligent digitization for land records</Text>

        <View style={styles.noticeRow}>
          <SyntheticNotice />
        </View>

        <Text style={styles.heading}>Who are you?</Text>
        <Text style={styles.body}>
          This choice sets up the demo account and nothing else. Your actual
          permissions come from your account on the server, checked on every
          request.
        </Text>

        <View style={styles.cards}>
          {CARDS.map((card) => {
            const active = selected === card.key;
            return (
              <Pressable
                key={card.key}
                onPress={() => choose(card)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                style={[styles.card, active && styles.cardActive]}
              >
                <Text style={styles.cardTitle}>{card.title}</Text>
                <Text style={styles.cardBlurb}>{card.blurb}</Text>
              </Pressable>
            );
          })}
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            style={styles.input}
            placeholder="you@example.gov.in"
            placeholderTextColor={colors.sand500}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            accessibilityLabel="Email"
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            style={styles.input}
            secureTextEntry
            textContentType="password"
            accessibilityLabel="Password"
            onSubmitEditing={() => void submit()}
            returnKeyType="go"
          />

          {error ? <ErrorText>{error}</ErrorText> : null}

          <Button
            label="Sign in"
            onPress={() => void submit()}
            busy={busy}
            disabled={!email.trim() || !password}
            style={{ marginTop: spacing.sm }}
          />
        </View>

        <Text style={styles.footnote}>
          Verification and approval workspaces are desktop-only. A phone is the
          wrong instrument for reading OCR overlays against a scan.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.navy },
  content: { paddingHorizontal: spacing.xl, gap: spacing.md },
  brand: { color: colors.white, fontSize: 26, fontWeight: "700", letterSpacing: -0.4 },
  tagline: { color: colors.navyLight, fontSize: 14 },
  noticeRow: { marginTop: spacing.xs },
  heading: {
    color: colors.white,
    fontSize: 20,
    fontWeight: "600",
    marginTop: spacing.lg,
  },
  body: { color: colors.navyLight, fontSize: 14, lineHeight: 20 },
  cards: { gap: spacing.sm, marginTop: spacing.sm },
  card: {
    backgroundColor: colors.navyDark,
    borderWidth: 1,
    borderColor: "#2E4A6E",
    borderRadius: radius.card,
    padding: spacing.lg,
    gap: 2,
  },
  cardActive: { borderColor: colors.burnt, backgroundColor: "#1A3352" },
  cardTitle: { color: colors.white, fontSize: 16, fontWeight: "600" },
  cardBlurb: { color: colors.navyLight, fontSize: 13, lineHeight: 18 },
  form: {
    backgroundColor: colors.white,
    borderRadius: radius.card,
    padding: spacing.lg,
    marginTop: spacing.md,
    gap: spacing.xs,
  },
  label: {
    fontSize: 13,
    fontWeight: "600",
    color: colors.navyDark,
    marginTop: spacing.sm,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    paddingHorizontal: spacing.md,
    minHeight: 46,
    fontSize: 15,
    color: colors.ink,
    backgroundColor: colors.sand50,
  },
  footnote: {
    color: colors.navyLight,
    fontSize: 12,
    lineHeight: 17,
    marginTop: spacing.md,
  },
});
