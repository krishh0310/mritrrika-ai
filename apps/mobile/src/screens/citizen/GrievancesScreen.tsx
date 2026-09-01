import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text,
  TextInput, View,
} from "react-native";

import { ApiError, api } from "../../api/client";
import { useIssueTypes, useMyGrievances } from "../../api/queries";
import {
  Button, Card, EmptyState, ErrorText, Eyebrow, Identifier, StatusChip,
} from "../../components/ui";
import type { CitizenStackParams } from "../../navigation";
import { colors, radius, spacing } from "../../theme";

const STATUS_TONES: Record<
  string,
  "neutral" | "progress" | "attention" | "good" | "bad"
> = {
  SUBMITTED: "neutral",
  OPEN: "neutral",
  UNDER_REVIEW: "progress",
  ACTION_REQUIRED: "attention",
  RESOLVED: "good",
  REJECTED: "bad",
};

/**
 * §19 — file and track. Officers review on the web; the phone is for filing.
 *
 * The issue type comes from the server's own list rather than a constant in
 * this file. It is a closed vocabulary the grievance service validates against,
 * so hard-coding it here would mean a rejected filing the moment the two
 * drifted, with a 422 the citizen cannot act on.
 */
export function GrievancesScreen() {
  const { params } = useRoute<RouteProp<CitizenStackParams, "Grievances">>();
  const queryClient = useQueryClient();

  const mine = useMyGrievances();
  const issueTypes = useIssueTypes();

  const [issueType, setIssueType] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Arriving from a parcel means the citizen is complaining about that parcel.
  // It is still only a default -- the server re-checks that they may reference
  // it, and refuses identically for "not yours" and "no such parcel" (§62).
  const parcelId = params?.parcelId ?? null;

  const chosen = issueType ?? issueTypes.data?.issue_types[0] ?? null;

  const file = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("issue_type", chosen ?? "OTHER");
      form.append("description", description.trim());
      if (parcelId) form.append("parcel_id", parcelId);
      return api.upload("/api/v1/grievances", form);
    },
    onSuccess: () => {
      setDescription("");
      setIssueType(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["grievances", "me"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError ? cause.message : "The grievance was not filed.",
      ),
  });

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <FlatList
        data={mine.data?.grievances ?? []}
        keyExtractor={(item) => item.grievance_id}
        contentContainerStyle={styles.list}
        refreshing={mine.isFetching}
        onRefresh={() => void mine.refetch()}
        ListHeaderComponent={
          <Card style={{ marginBottom: spacing.lg }}>
            <Eyebrow>Raise an issue</Eyebrow>

            {parcelId ? (
              <View style={styles.about}>
                <Text style={styles.aboutLabel}>About</Text>
                <Identifier>{parcelId}</Identifier>
                {params?.khasra ? (
                  <Text style={styles.aboutLabel}>Khasra {params.khasra}</Text>
                ) : null}
              </View>
            ) : null}

            <View style={styles.types}>
              {(issueTypes.data?.issue_types ?? []).map((type) => {
                const on = chosen === type;
                return (
                  <Pressable
                    key={type}
                    onPress={() => setIssueType(type)}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                    style={[styles.type, on && styles.typeActive]}
                  >
                    <Text style={[styles.typeLabel, on && styles.typeLabelActive]}>
                      {type.replace(/_/g, " ").toLowerCase()}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <TextInput
              style={styles.input}
              value={description}
              onChangeText={setDescription}
              multiline
              numberOfLines={4}
              placeholder="Say what the record shows and what it should show."
              placeholderTextColor={colors.sand300}
              textAlignVertical="top"
            />
            {error ? (
              <View style={{ marginTop: spacing.md }}>
                <ErrorText>{error}</ErrorText>
              </View>
            ) : null}
            <Button
              label="File it"
              onPress={() => file.mutate()}
              busy={file.isPending}
              disabled={description.trim().length === 0 || !chosen}
              style={{ marginTop: spacing.lg }}
            />
          </Card>
        }
        ListEmptyComponent={
          mine.isPending ? null : (
            <EmptyState
              title="You have not raised anything"
              description="If a record about your land looks wrong, describe it above."
            />
          )
        }
        renderItem={({ item }) => (
          <Card style={{ marginBottom: spacing.md }}>
            <View style={styles.rowTop}>
              <Identifier>{item.grievance_id}</Identifier>
              <StatusChip
                label={item.status.replace(/_/g, " ").toLowerCase()}
                tone={STATUS_TONES[item.status] ?? "neutral"}
              />
            </View>
            <Text style={styles.issue}>
              {item.issue_type.replace(/_/g, " ").toLowerCase()}
              {item.khasra_number ? ` · khasra ${item.khasra_number}` : ""}
            </Text>
            <Text style={styles.description}>{item.description}</Text>
            {item.resolution_note ? (
              <Text style={styles.note}>Officer: {item.resolution_note}</Text>
            ) : null}
          </Card>
        )}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  list: { padding: spacing.lg },
  about: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    backgroundColor: colors.sand50,
    borderRadius: radius.chip,
    gap: 2,
  },
  aboutLabel: { fontSize: 11, color: colors.sand500 },
  types: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
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
    marginTop: spacing.md,
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    padding: spacing.md,
    minHeight: 96,
    fontSize: 15,
    color: colors.ink,
  },
  rowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  issue: { fontSize: 13, color: colors.sand500, marginTop: spacing.sm },
  description: { fontSize: 14, color: colors.navyDark, marginTop: spacing.xs, lineHeight: 20 },
  note: {
    fontSize: 13,
    color: colors.sand700,
    marginTop: spacing.sm,
    backgroundColor: colors.sand50,
    padding: spacing.sm,
    borderRadius: radius.chip,
  },
});
