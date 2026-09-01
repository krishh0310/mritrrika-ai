import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useState } from "react";
import {
  Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View,
} from "react-native";

import { useLocations } from "../../api/queries";
import { Button, Card, Eyebrow } from "../../components/ui";
import { useConnectivity } from "../../net/connectivity";
import type { FieldStackParams } from "../../navigation";
import { uploadQueue } from "../../storage/upload-queue";
import { colors, radius, spacing } from "../../theme";

const DOCUMENT_TYPES = ["KHASRA", "KHATAUNI", "JAMABANDI", "MUTATION_REGISTER"];

/**
 * §21 metadata, entered on the phone.
 *
 * Queues first, uploads second — always, even with full signal. That ordering
 * is what makes the capture durable: if the app is killed mid-upload the page
 * is still on the device, still in the queue, and still gets sent.
 */
export function UploadMetadataScreen() {
  const { params } = useRoute<RouteProp<FieldStackParams, "UploadMetadata">>();
  const navigation =
    useNavigation<NativeStackNavigationProp<FieldStackParams>>();

  // The drain belongs to the provider. Calling drainQueue() here as well
  // would race the connectivity poll and could upload this page twice.
  const { online, refresh, syncNow } = useConnectivity();
  const villages = useLocations("VILLAGE");

  const [documentType, setDocumentType] = useState("KHASRA");
  const [villageId, setVillageId] = useState<string | null>(null);
  const [recordYear, setRecordYear] = useState("");
  const [khasra, setKhasra] = useState("");
  const [parcelId, setParcelId] = useState("");
  const [busy, setBusy] = useState(false);

  async function queueIt() {
    setBusy(true);
    const queued = await uploadQueue.add({
      uri: params.uri,
      fileName: params.fileName,
      documentType,
      villageId: villageId ?? undefined,
      recordYear: recordYear.trim() || undefined,
      khasraNumber: khasra.trim() || undefined,
      parcelId: parcelId.trim() || undefined,
    });
    await refresh();

    // Try immediately if there is signal. The status screen shows the outcome
    // either way, so nothing is lost when this fails.
    if (online) await syncNow().catch(() => undefined);

    setBusy(false);
    // replace, not navigate: going "back" from the status screen should return
    // to the queue, never to a metadata form for a page already captured.
    navigation.replace("UploadStatus", { queueId: queued.id });
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Image
          source={{ uri: params.uri }}
          style={styles.preview}
          resizeMode="contain"
          accessibilityLabel="The page you photographed"
        />

        <Card>
          <Eyebrow>Document type</Eyebrow>
          <View style={styles.types}>
            {DOCUMENT_TYPES.map((type) => (
              <Pressable
                key={type}
                onPress={() => setDocumentType(type)}
                accessibilityRole="radio"
                accessibilityState={{ selected: documentType === type }}
                style={[styles.type, documentType === type && styles.typeActive]}
              >
                <Text
                  style={[
                    styles.typeLabel,
                    documentType === type && styles.typeLabelActive,
                  ]}
                >
                  {type.replace(/_/g, " ")}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={{ height: spacing.lg }} />

          <Eyebrow>Village</Eyebrow>
          <View style={styles.types}>
            {(villages.data?.locations ?? []).map((village) => (
              <Pressable
                key={village.location_id}
                onPress={() =>
                  setVillageId(
                    villageId === village.location_id ? null : village.location_id,
                  )
                }
                accessibilityRole="radio"
                accessibilityState={{ selected: villageId === village.location_id }}
                style={[styles.type, villageId === village.location_id && styles.typeActive]}
              >
                <Text
                  style={[
                    styles.typeLabel,
                    villageId === village.location_id && styles.typeLabelActive,
                  ]}
                >
                  {village.name}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={{ height: spacing.lg }} />

          <Eyebrow>Record year</Eyebrow>
          <TextInput
            style={styles.input}
            value={recordYear}
            onChangeText={setRecordYear}
            placeholder="1998-99"
            placeholderTextColor={colors.sand300}
          />

          <View style={{ height: spacing.md }} />

          <Eyebrow>Khasra number</Eyebrow>
          <TextInput
            style={styles.input}
            value={khasra}
            onChangeText={setKhasra}
            placeholder="142/2"
            placeholderTextColor={colors.sand300}
          />

          <View style={{ height: spacing.md }} />

          <Eyebrow>Parcel identifier</Eyebrow>
          <TextInput
            style={[styles.input, styles.mono]}
            value={parcelId}
            onChangeText={setParcelId}
            autoCapitalize="characters"
            autoCorrect={false}
            placeholder="PARCEL-UP-DEMO-0142"
            placeholderTextColor={colors.sand300}
          />
          <Text style={styles.hint}>
            Linking the parcel lets the server check this page against the
            record&rsquo;s history.
          </Text>
        </Card>

        <Button label="Queue for upload" onPress={queueIt} busy={busy} />
        <Text style={styles.footnote}>
          The page is saved on this device first. If there is no signal it is
          sent as soon as the network returns.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  content: { padding: spacing.lg, gap: spacing.lg },
  preview: {
    width: "100%",
    height: 220,
    borderRadius: radius.card,
    backgroundColor: colors.sand100,
  },
  types: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  type: {
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  typeActive: { borderColor: colors.burnt, backgroundColor: colors.cream },
  typeLabel: { fontSize: 13, color: colors.sand700 },
  typeLabelActive: { color: colors.burnt, fontWeight: "600" },
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
  mono: { fontFamily: "Menlo", fontSize: 13 },
  hint: { fontSize: 12, color: colors.sand500, marginTop: spacing.sm },
  footnote: {
    fontSize: 12,
    color: colors.sand500,
    textAlign: "center",
    lineHeight: 18,
  },
});
