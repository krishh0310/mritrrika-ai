import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useRecordSearch, type SearchFilters } from "../../api/queries";
import {
  Button, Card, EmptyState, Eyebrow, Identifier, SyntheticNotice,
} from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, radius, spacing } from "../../theme";

/** §59 CitizenSearch — approved public records only (§17). */
export function CitizenSearchScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<CitizenStackParams>>();

  const [khasra, setKhasra] = useState("");
  const [owner, setOwner] = useState("");
  const [submitted, setSubmitted] = useState<SearchFilters | null>(null);

  const results = useRecordSearch(submitted ?? {}, submitted !== null);

  const canSearch = khasra.trim().length > 0 || owner.trim().length > 0;

  function run() {
    if (!canSearch) return;
    setSubmitted({
      khasra: khasra.trim() || undefined,
      owner_name: owner.trim() || undefined,
    });
  }

  return (
    <View style={styles.root}>
      <View style={styles.form}>
        <Eyebrow>Khasra number</Eyebrow>
        <TextInput
          style={styles.input}
          value={khasra}
          onChangeText={setKhasra}
          placeholder="142/2"
          placeholderTextColor={colors.sand300}
          returnKeyType="next"
        />

        <View style={{ height: spacing.md }} />

        <Eyebrow>Owner name</Eyebrow>
        <TextInput
          style={styles.input}
          value={owner}
          onChangeText={setOwner}
          placeholder="Ram Prasad"
          placeholderTextColor={colors.sand300}
          autoCorrect={false}
          returnKeyType="search"
          onSubmitEditing={run}
        />

        <Button
          label="Search"
          onPress={run}
          disabled={!canSearch}
          style={{ marginTop: spacing.md }}
        />
      </View>

      <FlatList
        data={results.data?.results ?? []}
        keyExtractor={(item) => item.parcel_id}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          submitted && results.data ? (
            <View style={styles.count}>
              <Text style={styles.countText}>
                {results.data.count} approved record
                {results.data.count === 1 ? "" : "s"}
              </Text>
              <SyntheticNotice />
            </View>
          ) : null
        }
        ListEmptyComponent={
          submitted === null ? (
            <EmptyState
              title="Search public records"
              description="Only approved records appear here. Nothing still in verification is searchable."
            />
          ) : results.isPending ? null : (
            <EmptyState
              title="No approved records match"
              description="Try a different khasra number."
            />
          )
        }
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
              <Text style={styles.khasra}>{item.khasra_number}</Text>
              <Identifier>{item.parcel_id}</Identifier>
              <Text style={styles.detail}>
                {item.village ?? "—"} · {item.area_value} {item.area_unit}
                {item.land_class ? ` · ${item.land_class}` : ""}
              </Text>
            </Card>
          </Pressable>
        )}
        ListFooterComponent={
          results.data && results.data.count > 0 ? (
            <Text style={styles.footnote}>
              Opening a record shows the full ownership history only if it is
              your own. Search shows what is public about an approved parcel;
              the history behind it is not (§17, §62).
            </Text>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  form: {
    padding: spacing.lg,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.sand200,
  },
  input: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    paddingHorizontal: spacing.md,
    minHeight: 46,
    fontSize: 15,
    color: colors.ink,
  },
  list: { padding: spacing.lg },
  count: { marginBottom: spacing.md, gap: spacing.sm },
  countText: { fontSize: 14, color: colors.sand700 },
  khasra: { fontSize: 20, fontWeight: "600", color: colors.navyDark },
  detail: { fontSize: 14, color: colors.sand700, marginTop: spacing.sm },
  footnote: { fontSize: 12, color: colors.sand500, lineHeight: 18 },
});
