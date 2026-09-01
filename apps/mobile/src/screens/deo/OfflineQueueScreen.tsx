import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import {
  Button, Card, EmptyState, Identifier, StatusChip,
} from "../../components/ui";
import { useConnectivity } from "../../net/connectivity";
import type { FieldStackParams } from "../../navigation";
import { uploadQueue, type QueuedUpload } from "../../storage/upload-queue";
import { colors, spacing } from "../../theme";

/** §60's status vocabulary, in the operator's words. */
const STATUS_LABELS: Record<
  QueuedUpload["status"],
  { label: string; tone: "neutral" | "progress" | "attention" | "good" | "bad" }
> = {
  QUEUED: { label: "Queued", tone: "neutral" },
  WAITING_FOR_NETWORK: { label: "Waiting for network", tone: "attention" },
  UPLOADING: { label: "Uploading", tone: "progress" },
  UPLOADED: { label: "Uploaded", tone: "good" },
  FAILED: { label: "Failed", tone: "bad" },
};

export function OfflineQueueScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<FieldStackParams>>();

  // All queue state comes from the provider, which owns the only drain. A
  // second drain started from this screen could upload the same photograph
  // twice, so "Upload now" asks the provider rather than calling drainQueue.
  const { items, pending, online, syncing, syncNow, refresh } = useConnectivity();
  const sent = items.length - pending.length;

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <Text style={styles.count}>
            {pending.length} waiting · {sent} sent
          </Text>
          <StatusChip
            label={online ? "Online" : "No network"}
            tone={online ? "good" : "attention"}
          />
        </View>
        <View style={styles.actions}>
          <Button
            label="Upload now"
            onPress={() => void syncNow()}
            busy={syncing}
            disabled={pending.length === 0 || !online}
            style={{ flex: 1 }}
          />
          <Button
            label="Clear sent"
            variant="outline"
            onPress={async () => {
              await uploadQueue.clearUploaded();
              await refresh();
            }}
            disabled={sent === 0}
            style={{ flex: 1 }}
          />
        </View>
        {!online ? (
          <Text style={styles.offline}>
            Everything here is safe on this device and is sent automatically
            when the network returns.
          </Text>
        ) : null}
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshing={syncing}
        onRefresh={() => void syncNow()}
        ListEmptyComponent={
          <EmptyState
            title="Nothing captured yet"
            description="Photographs you take are held here until they reach the server."
          />
        }
        renderItem={({ item }) => {
          const status = STATUS_LABELS[item.status];
          return (
            <Pressable
              onPress={() => navigation.navigate("UploadStatus", { queueId: item.id })}
              accessibilityRole="button"
              accessibilityLabel={`${item.documentType.replace(/_/g, " ")}, ${status.label}`}
            >
              <Card style={{ marginBottom: spacing.md }}>
                <View style={styles.rowTop}>
                  <Text style={styles.type}>{item.documentType.replace(/_/g, " ")}</Text>
                  <StatusChip label={status.label} tone={status.tone} />
                </View>

                <Text style={styles.meta}>
                  Captured {new Date(item.capturedAt).toLocaleString()}
                </Text>

                {item.khasraNumber ? (
                  <Text style={styles.meta}>Khasra {item.khasraNumber}</Text>
                ) : null}
                {item.parcelId ? <Identifier>{item.parcelId}</Identifier> : null}
                {item.documentId ? (
                  <View style={{ marginTop: spacing.sm }}>
                    <Identifier>{item.documentId}</Identifier>
                  </View>
                ) : null}

                {item.lastError ? (
                  <Text style={styles.error}>
                    {item.lastError}
                    {item.attempts > 1 ? ` (${item.attempts} attempts)` : ""}
                  </Text>
                ) : null}
              </Card>
            </Pressable>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  header: {
    padding: spacing.lg,
    gap: spacing.md,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.sand200,
  },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  count: { fontSize: 15, color: colors.navyDark, fontWeight: "600" },
  actions: { flexDirection: "row", gap: spacing.md },
  offline: { fontSize: 12, color: colors.sand500, lineHeight: 17 },
  list: { padding: spacing.lg },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  type: { fontSize: 15, fontWeight: "600", color: colors.navyDark },
  meta: { fontSize: 13, color: colors.sand500, marginTop: spacing.xs },
  error: { fontSize: 13, color: colors.low, marginTop: spacing.sm },
});
