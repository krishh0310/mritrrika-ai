import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from "react-native";

import { ApiError, api } from "../../api/client";
import type { AiAnswer } from "../../api/queries";
import {
  Button, Card, ErrorText, Eyebrow, Identifier, StatusChip, SyntheticNotice,
} from "../../components/ui";
import { colors, radius, spacing } from "../../theme";

/**
 * Ask about your land (§18, §35).
 *
 * Authorization happens on the server before retrieval, so the model is never
 * shown a record the asker could not already read. The screen's job is to make
 * the grounding visible: every answer is rendered with the citations it was
 * built from, and an answer that arrived without an LLM says so rather than
 * quietly looking the same as one that had one (§82).
 */

const SUGGESTIONS = [
  "What land do I own?",
  "Who owned my parcel before me?",
  "What mutations affected my land?",
  "How much total area is recorded in my name?",
];

export function AssistantScreen() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: (text: string) =>
      api.post<AiAnswer>("/api/v1/ai/query", { question: text, explain: true }),
    onMutate: (text) => {
      setAsked(text);
      setError(null);
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The assistant could not answer that.",
      ),
  });

  function submit(text: string) {
    const trimmed = text.trim();
    // The API rejects anything under three characters; catching it here saves
    // a round trip and a 422 the asker cannot act on.
    if (trimmed.length < 3) return;
    setQuestion(trimmed);
    ask.mutate(trimmed);
  }

  const answer = ask.data;

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Card>
          <Eyebrow>Your question</Eyebrow>
          <TextInput
            style={styles.input}
            value={question}
            onChangeText={setQuestion}
            multiline
            placeholder="Ask about your own land records."
            placeholderTextColor={colors.sand300}
            textAlignVertical="top"
          />
          <Button
            label="Ask"
            onPress={() => submit(question)}
            busy={ask.isPending}
            disabled={question.trim().length < 3}
            style={{ marginTop: spacing.md }}
          />
        </Card>

        {!asked ? (
          <View style={styles.suggestions}>
            <Eyebrow>Try asking</Eyebrow>
            {SUGGESTIONS.map((suggestion) => (
              <Pressable
                key={suggestion}
                onPress={() => submit(suggestion)}
                accessibilityRole="button"
                style={styles.suggestion}
              >
                <Text style={styles.suggestionText}>{suggestion}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {error ? <ErrorText>{error}</ErrorText> : null}

        {answer ? (
          <Card style={{ gap: spacing.sm }}>
            <View style={styles.answerHead}>
              <Eyebrow>Answer</Eyebrow>
              {answer.degraded || !answer.llm_used ? (
                <StatusChip label="Records only" tone="attention" />
              ) : null}
            </View>

            <Text style={styles.answer}>{answer.answer}</Text>

            {answer.degraded || !answer.llm_used ? (
              <Text style={styles.degraded}>
                No language model was reachable, so this is assembled straight
                from your records rather than written up.
              </Text>
            ) : null}

            <View style={styles.citations}>
              <Eyebrow>Based on</Eyebrow>
              {answer.citations.length === 0 ? (
                <Text style={styles.noCitations}>
                  No records were cited, so treat this as general guidance
                  rather than a statement about your land.
                </Text>
              ) : (
                answer.citations.map((citation, index) => (
                  <View key={`${citation.id}-${index}`} style={styles.citation}>
                    <Identifier>{citation.id}</Identifier>
                    <Text style={styles.citationDetail}>
                      {citation.detail ?? citation.type.replace(/_/g, " ")}
                    </Text>
                  </View>
                ))
              )}
            </View>

            <SyntheticNotice />
          </Card>
        ) : null}

        <Text style={styles.note}>
          The assistant can only reach records you are already allowed to see.
          It is checked on the server before anything is retrieved (§18).
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.offwhite },
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  input: {
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    padding: spacing.md,
    minHeight: 88,
    fontSize: 15,
    color: colors.ink,
  },
  suggestions: { gap: spacing.sm },
  suggestion: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.sand200,
    borderRadius: radius.card,
    padding: spacing.md,
  },
  suggestionText: { fontSize: 14, color: colors.navyDark },
  answerHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  answer: { fontSize: 15, lineHeight: 23, color: colors.ink },
  degraded: { fontSize: 12, lineHeight: 17, color: colors.medium },
  citations: {
    marginTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.sand100,
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  citation: { gap: 2 },
  citationDetail: { fontSize: 13, color: colors.sand700 },
  noCitations: { fontSize: 13, color: colors.medium, lineHeight: 19 },
  note: { fontSize: 12, lineHeight: 18, color: colors.sand500 },
});
