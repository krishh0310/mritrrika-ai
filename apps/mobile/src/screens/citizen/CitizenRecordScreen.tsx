import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError } from "../../api/client";
import { useOwnershipHistory, useParcelDetail } from "../../api/queries";
import {
  Button, Card, EmptyState, ErrorText, Eyebrow, Identifier, SyntheticNotice,
} from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, spacing } from "../../theme";

/**
 * §59 CitizenRecord — one parcel's ownership history.
 *
 * §17 keeps machine detail off this screen entirely: no raw OCR, no
 * confidence, no verification notes. A citizen gets the approved record.
 */
export function CitizenRecordScreen() {
  const { params } = useRoute<RouteProp<CitizenStackParams, "CitizenRecord">>();
  const navigation =
    useNavigation<NativeStackNavigationProp<CitizenStackParams>>();

  const parcel = useParcelDetail(params.parcelId);
  const history = useOwnershipHistory(params.parcelId);

  const spans = history.data?.history ?? [];
  const detail = parcel.data;

  // A parcel the caller does not hold comes back 403, and deliberately looks
  // the same as one that does not exist (§62). Saying "not yours" would leak
  // that it exists.
  const denied =
    (parcel.error instanceof ApiError && parcel.error.isForbidden) ||
    (history.error instanceof ApiError && history.error.isForbidden);

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Identifier>{params.parcelId}</Identifier>
        <SyntheticNotice />
      </View>

      {denied ? (
        <ErrorText>
          This record is not available to you. You can only open records linked
          to your own owner identity.
        </ErrorText>
      ) : null}

      {detail ? (
        <Card>
          <Eyebrow>The record</Eyebrow>
          <Text style={styles.khasra}>Khasra {detail.khasra_number}</Text>
          <View style={styles.grid}>
            <Cell label="Khata" value={detail.khata_number} />
            <Cell
              label="Area"
              value={`${detail.area_value} ${detail.area_unit_raw ?? detail.area_unit}`}
            />
            <Cell label="Class" value={detail.land_class} />
          </View>
        </Card>
      ) : null}

      <Card>
        <Eyebrow>Ownership and mutation history</Eyebrow>
        {history.isPending ? (
          <Text style={styles.muted}>Loading…</Text>
        ) : spans.length === 0 ? (
          <EmptyState
            title="No history recorded"
            description="Only the current holding is on file for this parcel."
          />
        ) : (
          <View style={{ marginTop: spacing.md }}>
            {spans.map((span, index) => (
              <View
                key={`${span.owner_id}-${span.valid_from}-${index}`}
                style={styles.span}
              >
                <View
                  style={[
                    styles.marker,
                    span.valid_to === null && styles.markerCurrent,
                  ]}
                >
                  <Text
                    style={[
                      styles.markerText,
                      span.valid_to === null && styles.markerTextCurrent,
                    ]}
                  >
                    {span.valid_from.slice(0, 4)}
                  </Text>
                </View>

                <View style={styles.spanBody}>
                  <Text style={styles.owner}>{span.owner}</Text>
                  <Text style={styles.muted}>
                    Share {span.share} ·{" "}
                    {span.valid_to ? `until ${span.valid_to}` : "current holder"}
                  </Text>
                  {span.mutation_number ? (
                    <Text style={styles.mutation}>
                      Mutation {span.mutation_number}
                      {span.mutation_type
                        ? ` · ${span.mutation_type.replace(/_/g, " ").toLowerCase()}`
                        : ""}
                    </Text>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        )}
      </Card>

      {denied ? null : (
        <Button
          label="Something here is wrong"
          variant="outline"
          onPress={() =>
            navigation.navigate("Grievances", {
              parcelId: params.parcelId,
              khasra: params.khasra ?? detail?.khasra_number,
            })
          }
        />
      )}
    </ScrollView>
  );
}

function Cell({ label, value }: { label: string; value: string | null }) {
  return (
    <View style={styles.cell}>
      <Eyebrow>{label}</Eyebrow>
      <Text style={styles.cellValue}>{value ?? "—"}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  content: { padding: spacing.lg, gap: spacing.lg },
  header: { gap: spacing.sm },
  khasra: { fontSize: 22, fontWeight: "600", color: colors.navyDark, marginTop: 2 },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.sand100,
    paddingTop: spacing.md,
  },
  cell: { width: "50%", paddingVertical: spacing.xs, paddingRight: spacing.sm },
  cellValue: { fontSize: 15, color: colors.navyDark, marginTop: 2 },
  span: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.lg },
  marker: {
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: colors.sand200,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  markerCurrent: { borderColor: colors.burnt, backgroundColor: colors.cream },
  markerText: { fontFamily: "Menlo", fontSize: 12, color: colors.sand700 },
  markerTextCurrent: { color: colors.burnt, fontWeight: "700" },
  spanBody: { flex: 1, paddingTop: spacing.xs },
  owner: { fontSize: 16, fontWeight: "600", color: colors.navyDark },
  muted: { fontSize: 13, color: colors.sand500, marginTop: 2 },
  mutation: { fontSize: 12, color: colors.sand700, marginTop: spacing.xs },
});
