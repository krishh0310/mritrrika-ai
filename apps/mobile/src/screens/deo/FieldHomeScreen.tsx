import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useAuth } from "../../auth/auth-context";
import { Button, Card, Eyebrow, StatusChip, SyntheticNotice } from "../../components/ui";
import { useConnectivity } from "../../net/connectivity";
import type { FieldStackParams } from "../../navigation";
import { colors, spacing } from "../../theme";

/** §59 — the field operator's home. Capture, then queue. */
export function FieldHomeScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<FieldStackParams>>();
  const { user, signOut } = useAuth();

  // The queue count comes from the provider rather than a local poll, so this
  // number and the one on the queue screen cannot disagree.
  const { online, pending, syncing } = useConnectivity();

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.name}>{user?.full_name}</Text>
        <SyntheticNotice />
      </View>

      <Card>
        <Eyebrow>Capture</Eyebrow>
        <Text style={styles.body}>
          Photograph a legacy record. It is saved on this device first, then
          sent when there is signal.
        </Text>
        <Button
          label="Photograph a record"
          variant="accent"
          onPress={() => navigation.navigate("CameraUpload")}
          style={{ marginTop: spacing.lg }}
        />
      </Card>

      <Card>
        <View style={styles.queueRow}>
          <View>
            <Eyebrow>Upload queue</Eyebrow>
            <Text style={styles.pending}>
              {pending.length} waiting to be sent
            </Text>
          </View>
          <StatusChip
            label={syncing ? "Sending" : online ? "Online" : "No network"}
            tone={syncing ? "progress" : online ? "good" : "attention"}
          />
        </View>
        <Button
          label="Open the queue"
          variant="outline"
          onPress={() => navigation.navigate("OfflineQueue")}
          style={{ marginTop: spacing.lg }}
        />
      </Card>

      <Text style={styles.note}>
        Verification and approval need a large screen. Open the web application
        on a desktop for those.
      </Text>

      <Button label="Sign out" variant="ghost" onPress={() => void signOut()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  content: { padding: spacing.lg, gap: spacing.lg },
  header: { gap: spacing.sm },
  name: { fontSize: 22, fontWeight: "700", color: colors.navyDark },
  body: { fontSize: 14, color: colors.sand700, marginTop: spacing.sm, lineHeight: 20 },
  queueRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  pending: { fontSize: 18, fontWeight: "600", color: colors.navyDark, marginTop: 2 },
  note: {
    fontSize: 13,
    color: colors.sand500,
    textAlign: "center",
    lineHeight: 19,
  },
});
