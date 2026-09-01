import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { useCitizenDashboard, useMyGrievances, useMyParcels } from "../../api/queries";
import { useAuth } from "../../auth/auth-context";
import { Button, Card, ErrorText, Eyebrow, SyntheticNotice } from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, radius, spacing } from "../../theme";

type Props = NativeStackScreenProps<CitizenStackParams, "CitizenDashboard">;

/**
 * §59 CitizenDashboard — "what do I hold, and what needs my attention?"
 *
 * A hub, not a data screen. The holdings themselves live on My Land; putting
 * them here too would mean two places to keep in step and neither being the
 * obvious one to open. Everything shown derives from the caller's own session:
 * there is no owner picker in this app because the API accepts no owner id
 * (§62).
 */
export function CitizenDashboardScreen({ navigation }: Props) {
  const { user, signOut } = useAuth();
  const dashboard = useCitizenDashboard();
  const parcels = useMyParcels();
  const grievances = useMyGrievances();

  const refreshing =
    dashboard.isRefetching || parcels.isRefetching || grievances.isRefetching;

  function refresh() {
    void dashboard.refetch();
    void parcels.refetch();
    void grievances.refetch();
  }

  // "Needs attention" is anything an officer has not closed out. RESOLVED and
  // REJECTED are both finished as far as the citizen's to-do list goes.
  const counts = grievances.data?.counts_by_status;
  const openGrievances = counts
    ? Object.entries(counts)
        .filter(([status]) => status !== "RESOLVED" && status !== "REJECTED")
        .reduce((total, [, n]) => total + n, 0)
    : null;

  const summary = dashboard.data;

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <View style={styles.header}>
        <Eyebrow>Signed in as</Eyebrow>
        <Text style={styles.name}>
          {summary?.citizen_name ?? user?.full_name ?? "—"}
        </Text>
        <SyntheticNotice />
      </View>

      {dashboard.isError ? (
        <ErrorText>
          {dashboard.error instanceof Error
            ? dashboard.error.message
            : "Could not load your dashboard."}
        </ErrorText>
      ) : null}

      <View style={styles.stats}>
        <Stat label="Parcels" value={summary ? String(summary.parcel_count) : "—"} />
        <Stat
          label={
            summary?.area_units.length
              ? `Total area (${summary.area_units.join(", ")})`
              : "Total area"
          }
          value={summary ? formatArea(summary.total_area) : "—"}
        />
        <Stat
          label="Open grievances"
          value={openGrievances === null ? "—" : String(openGrievances)}
        />
      </View>

      <Card style={styles.actions}>
        <Text style={styles.sectionTitle}>What would you like to do?</Text>
        <Button
          label={`My Land${parcels.data ? ` (${parcels.data.count})` : ""}`}
          onPress={() => navigation.navigate("MyLand")}
        />
        <Button
          label="Search records"
          variant="outline"
          onPress={() => navigation.navigate("CitizenSearch")}
        />
        <Button
          label="Parcel map"
          variant="outline"
          onPress={() => navigation.navigate("CitizenMap")}
        />
        <Button
          label="Grievances"
          variant="outline"
          onPress={() => navigation.navigate("Grievances")}
        />
        <Button
          label="Ask about your land"
          variant="accent"
          onPress={() => navigation.navigate("Assistant")}
        />
      </Card>

      <Text style={styles.note}>
        You see only the records linked to your own owner identity. Search
        returns approved records and never pipeline internals — no raw OCR, no
        confidence scores, no verification notes (§17).
      </Text>

      <Button label="Sign out" variant="ghost" onPress={() => void signOut()} />
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

/** Areas arrive as floats; two decimals is the precision a khasra entry carries. */
function formatArea(value: number): string {
  return value.toFixed(2).replace(/\.00$/, "");
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  header: { gap: spacing.xs },
  name: { fontSize: 22, fontWeight: "700", color: colors.navyDark },
  stats: { flexDirection: "row", gap: spacing.sm },
  stat: {
    flex: 1,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    padding: spacing.md,
    gap: 2,
  },
  statValue: { fontSize: 22, fontWeight: "700", color: colors.navy },
  statLabel: { fontSize: 11, color: colors.sand500, lineHeight: 15 },
  actions: { gap: spacing.sm },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "600",
    color: colors.navyDark,
    marginBottom: spacing.xs,
  },
  note: { fontSize: 12, lineHeight: 18, color: colors.sand500 },
});
