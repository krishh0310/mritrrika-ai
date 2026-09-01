import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useAuth } from "../auth/auth-context";
import { primaryRole, ROLE_LABELS } from "../auth/roles";
import { Button, Card, Eyebrow, SyntheticNotice } from "../components/ui";
import { colors, spacing } from "../theme";

/**
 * An honest dead end, for roles whose work is not on the phone (§4).
 *
 * A verifier holds a scan against an OCR overlay and corrects fields; a
 * tehsildar reads an anomaly report before approving. Neither fits a phone
 * screen, and neither role is granted `document:upload`, so there is no
 * capture arm to offer them either. Saying that plainly beats a portal of
 * buttons that all refuse.
 */
export function DesktopOnlyScreen() {
  const { user, signOut } = useAuth();
  const role = user ? ROLE_LABELS[primaryRole(user.roles)] : null;

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Eyebrow>Signed in as</Eyebrow>
        <Text style={styles.name}>{user?.full_name}</Text>
        {role ? <Text style={styles.role}>{role}</Text> : null}
        <SyntheticNotice />
      </View>

      <Card style={{ gap: spacing.md }}>
        <Text style={styles.title}>Your work is on the desktop</Text>
        <Text style={styles.body}>
          Reviewing extraction against a scan, correcting fields, and approving
          records all need a large screen. Open the Mrittika web application on
          a computer to do them.
        </Text>
        <Text style={styles.body}>
          The mobile app covers citizen access and field capture only.
        </Text>
      </Card>

      <Button label="Sign out" variant="outline" onPress={() => void signOut()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.lg },
  header: { gap: spacing.xs },
  name: { fontSize: 22, fontWeight: "700", color: colors.navyDark },
  role: { fontSize: 14, color: colors.sand700 },
  title: { fontSize: 17, fontWeight: "600", color: colors.navyDark },
  body: { fontSize: 15, lineHeight: 22, color: colors.sand700 },
});
