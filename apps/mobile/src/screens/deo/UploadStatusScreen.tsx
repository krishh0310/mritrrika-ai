import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, api } from "../../api/client";
import { useProcessingStatus } from "../../api/queries";
import {
  Button, Card, ErrorText, Eyebrow, Identifier, StatusChip, SyntheticNotice,
} from "../../components/ui";
import { useConnectivity } from "../../net/connectivity";
import type { FieldStackParams } from "../../navigation";
import { colors, spacing } from "../../theme";

/**
 * §59 UploadStatus — one capture, all the way through (§60).
 *
 * §60 asks for a single legible progression:
 *
 *   Waiting for network -> Queued -> Uploading -> Uploaded -> Processing -> Completed
 *
 * The first four states live on the device, in the upload queue. The last two
 * live on the server, and are only knowable once the document has an id. This
 * screen is the one place both halves are shown as one line, because to the
 * operator who photographed the page it is one thing happening.
 */

/** §24's stages, in the order the pipeline runs them. */
const STAGES = [
  { key: "upload", label: "Upload" },
  { key: "quality", label: "Quality check" },
  { key: "preprocessing", label: "Enhancement" },
  { key: "ocr", label: "Text recognition" },
  { key: "layout", label: "Layout" },
  { key: "extraction", label: "Field extraction" },
  { key: "normalization", label: "Normalization" },
  { key: "validation", label: "Validation" },
  { key: "confidence", label: "Confidence" },
  { key: "complete", label: "Ready for verification" },
] as const;

const QUEUE_LABELS: Record<
  string,
  { label: string; tone: "neutral" | "progress" | "attention" | "good" | "bad" }
> = {
  QUEUED: { label: "Queued", tone: "neutral" },
  WAITING_FOR_NETWORK: { label: "Waiting for network", tone: "attention" },
  UPLOADING: { label: "Uploading", tone: "progress" },
  UPLOADED: { label: "Uploaded", tone: "good" },
  FAILED: { label: "Failed", tone: "bad" },
};

export function UploadStatusScreen() {
  const { params } = useRoute<RouteProp<FieldStackParams, "UploadStatus">>();
  const { items, online, syncing, syncNow } = useConnectivity();
  const [error, setError] = useState<string | null>(null);

  const item = items.find((candidate) => candidate.id === params.queueId) ?? null;
  const documentId = item?.documentId ?? null;
  const status = useProcessingStatus(documentId);

  const start = useMutation({
    mutationFn: async () => {
      try {
        return await api.post(`/api/v1/documents/${documentId}/process`, {});
      } catch (cause) {
        // 503 means no Celery broker is reachable. The endpoint itself
        // suggests the inline path for exactly this case, so take it rather
        // than making the operator diagnose a message about Redis.
        if (cause instanceof ApiError && cause.status === 503) {
          return api.post(
            `/api/v1/documents/${documentId}/process?synchronous=true`,
            {},
          );
        }
        throw cause;
      }
    },
    onMutate: () => setError(null),
    onSuccess: () => void status.refetch(),
    onError: (cause) =>
      setError(
        cause instanceof ApiError ? cause.message : "Processing did not start.",
      ),
  });

  if (!item) {
    return (
      <View style={styles.gone}>
        <Text style={styles.goneTitle}>This capture is no longer in the queue</Text>
        <Text style={styles.goneBody}>
          It was either sent and cleared, or removed from this device.
        </Text>
      </View>
    );
  }

  const queue = QUEUE_LABELS[item.status] ?? QUEUE_LABELS.QUEUED;
  const pipeline = status.data;
  const currentStage = pipeline
    ? STAGES.findIndex((stage) => stage.key === pipeline.stage)
    : -1;
  const failed = pipeline?.status === "FAILED";
  const done = pipeline?.status === "SUCCEEDED";

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Eyebrow>{item.documentType.replace(/_/g, " ")}</Eyebrow>
        <Text style={styles.captured}>
          Captured {new Date(item.capturedAt).toLocaleString()}
        </Text>
        <SyntheticNotice />
      </View>

      <Card style={{ gap: spacing.sm }}>
        <View style={styles.row}>
          <Eyebrow>On this device</Eyebrow>
          <StatusChip label={queue.label} tone={queue.tone} />
        </View>

        {item.khasraNumber ? (
          <Text style={styles.meta}>Khasra {item.khasraNumber}</Text>
        ) : null}
        {item.recordYear ? (
          <Text style={styles.meta}>Record year {item.recordYear}</Text>
        ) : null}
        {item.parcelId ? <Identifier>{item.parcelId}</Identifier> : null}

        {item.lastError ? (
          <Text style={styles.failure}>
            {item.lastError}
            {item.attempts > 1 ? ` (${item.attempts} attempts)` : ""}
          </Text>
        ) : null}

        {item.status !== "UPLOADED" ? (
          <>
            <Button
              label={online ? "Send it now" : "Waiting for network"}
              onPress={() => void syncNow()}
              busy={syncing}
              disabled={!online}
              style={{ marginTop: spacing.sm }}
            />
            {!online ? (
              <Text style={styles.note}>
                The page is safe on this device. It is sent automatically as
                soon as there is signal — you do not need to come back here.
              </Text>
            ) : null}
          </>
        ) : null}
      </Card>

      {documentId ? (
        <Card style={{ gap: spacing.sm }}>
          <View style={styles.row}>
            <Eyebrow>On the server</Eyebrow>
            <StatusChip
              label={
                failed ? "Failed" : done ? "Completed" : pipeline ? "Processing" : "Uploaded"
              }
              tone={failed ? "bad" : done ? "good" : "progress"}
            />
          </View>
          <Identifier>{documentId}</Identifier>

          {error ? <ErrorText>{error}</ErrorText> : null}

          {!pipeline || pipeline.status === "NOT_STARTED" ? (
            <>
              <Text style={styles.note}>
                The page is stored and its quality has been scored. Processing
                runs the §23 pipeline over it.
              </Text>
              <Button
                label="Start processing"
                onPress={() => start.mutate()}
                busy={start.isPending}
                style={{ marginTop: spacing.sm }}
              />
            </>
          ) : (
            <View style={styles.stages}>
              {STAGES.map((stage, index) => {
                const reached = currentStage >= 0 && index <= currentStage;
                const isCurrent = index === currentStage && !done;
                return (
                  <View key={stage.key} style={styles.stage}>
                    <View
                      style={[
                        styles.dot,
                        (reached || done) && styles.dotDone,
                        isCurrent && !failed && styles.dotCurrent,
                        isCurrent && failed && styles.dotFailed,
                      ]}
                    />
                    <Text
                      style={[
                        styles.stageLabel,
                        (reached || done) && styles.stageLabelDone,
                      ]}
                    >
                      {stage.label}
                    </Text>
                  </View>
                );
              })}
            </View>
          )}

          {pipeline?.message ? (
            <Text style={styles.meta}>{pipeline.message}</Text>
          ) : null}
          {pipeline?.error ? <ErrorText>{pipeline.error}</ErrorText> : null}

          {done ? (
            <Text style={styles.note}>
              Extraction is done and this document is waiting for a verifier.
              That review happens on the web application, on a desktop.
            </Text>
          ) : null}
        </Card>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  header: { gap: spacing.xs },
  captured: { fontSize: 16, fontWeight: "600", color: colors.navyDark },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  meta: { fontSize: 13, color: colors.sand700 },
  failure: { fontSize: 13, color: colors.low },
  note: { fontSize: 12, lineHeight: 18, color: colors.sand500 },
  stages: { marginTop: spacing.sm, gap: spacing.sm },
  stage: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: colors.sand300,
    backgroundColor: colors.white,
  },
  dotDone: { backgroundColor: colors.high, borderColor: colors.high },
  dotCurrent: { backgroundColor: colors.burnt, borderColor: colors.burnt },
  dotFailed: { backgroundColor: colors.low, borderColor: colors.low },
  stageLabel: { fontSize: 14, color: colors.sand500 },
  stageLabelDone: { color: colors.navyDark },
  gone: { flex: 1, justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  goneTitle: { fontSize: 17, fontWeight: "600", color: colors.navyDark },
  goneBody: { fontSize: 14, color: colors.sand500, lineHeight: 20 },
});
