import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { useMyParcels } from "../../api/queries";
import {
  Button, Card, EmptyState, ErrorText, Eyebrow, Identifier, SyntheticNotice,
} from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, spacing } from "../../theme";

/**
 * §59 MyLand — the holder's own parcels, derived from their session.
 *
 * The list takes no owner parameter, because /citizen/my-parcels accepts none:
 * the server resolves the holder from the token (§62). There is no way to make
 * this screen show someone else's land, which is the point.
 */
export function MyLandScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<CitizenStackParams>>();
  const parcels = useMyParcels();

  return (
    <View style={styles.root}>
      <FlatList
        data={parcels.data?.parcels ?? []}
        keyExtractor={(item) => item.parcel_id}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.count}>
              {parcels.data
                ? `${parcels.data.count} parcel${parcels.data.count === 1 ? "" : "s"} recorded against your name`
                : "Loading your holdings…"}
            </Text>
            <SyntheticNotice />
            {parcels.isError ? (
              <ErrorText>Could not load your parcels. Pull down to try again.</ErrorText>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          parcels.isPending ? null : (
            <EmptyState
              title="No parcels recorded against your name"
              description="A parcel appears once a tehsildar approves a record naming you as a holder."
            />
          )
        }
        refreshing={parcels.isFetching}
        onRefresh={() => void parcels.refetch()}
        renderItem={({ item }) => (
          <Pressable
            onPress={() =>
              navigation.navigate("CitizenRecord", {
                parcelId: item.parcel_id,
                khasra: item.khasra_number,
              })
            }
            accessibilityRole="button"
            accessibilityLabel={`Khasra ${item.khasra_number}, open the record`}
          >
            <Card style={{ marginBottom: spacing.md }}>
              <Eyebrow>Khasra</Eyebrow>
              <Text style={styles.khasra}>{item.khasra_number}</Text>
              <Identifier>{item.parcel_id}</Identifier>

              <View style={styles.grid}>
                <Cell label="Village" value={item.village} />
                <Cell
                  label="Area"
                  value={`${item.area_value} ${item.area_unit_raw ?? item.area_unit}`}
                />
                <Cell label="Your share" value={item.share} />
                <Cell label="Class" value={item.land_class} />
              </View>

              {item.village_id ? (
                <Button
                  label="See it on the map"
                  variant="ghost"
                  style={{ marginTop: spacing.sm, alignSelf: "flex-start" }}
                  onPress={() =>
                    navigation.navigate("CitizenMap", {
                      villageId: item.village_id ?? undefined,
                      villageName: item.village ?? undefined,
                      highlight: item.parcel_id,
                    })
                  }
                />
              ) : null}
            </Card>
          </Pressable>
        )}
      />
    </View>
  );
}

function Cell({ label, value }: { label: string; value: string | null }) {
  return (
    <View style={styles.cell}>
      <Eyebrow>{label}</Eyebrow>
      <Text style={styles.value}>{value ?? "—"}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  list: { padding: spacing.lg },
  header: { gap: spacing.sm, marginBottom: spacing.lg },
  count: { fontSize: 15, color: colors.sand700 },
  khasra: { fontSize: 24, fontWeight: "600", color: colors.navyDark, marginTop: 2 },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.sand100,
    paddingTop: spacing.md,
  },
  cell: { width: "50%", paddingVertical: spacing.xs, paddingRight: spacing.sm },
  value: { fontSize: 15, color: colors.navyDark, marginTop: 2 },
});
