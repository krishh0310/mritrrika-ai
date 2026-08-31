"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CornerDownLeft, Database, Sparkles } from "lucide-react";

import { ApiError, api } from "@/lib/api-client";
import type { AiAnswer } from "@/lib/queries";
import { Button, Card, Input, cn } from "@mrittika/ui";

/**
 * The grounded assistant (§18, §35).
 *
 * Two things this component insists on:
 *
 *   1. **Citations are not optional.** Every answer renders the records it was
 *      built from. §9 says the database is the source of truth and the model
 *      only explains it, so an answer with nothing behind it is shown as a
 *      failure to answer, not as an answer.
 *   2. **Degraded mode is visible.** When no LLM is reachable the API still
 *      returns the structured result (§82). The UI says so rather than
 *      passing a database lookup off as a generated answer.
 */

type Turn = { question: string; answer?: AiAnswer; error?: string };

export function AiAssistant({
  suggestions,
  initialQuestion,
  placeholder = "Ask about your land records…",
}: {
  suggestions: string[];
  initialQuestion?: string;
  placeholder?: string;
}) {
  const [question, setQuestion] = useState(initialQuestion ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const transcript = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) =>
      api.post<AiAnswer>("/api/v1/ai/query", { question: q, explain: true }),
    onMutate: (q) => setTurns((prior) => [...prior, { question: q }]),
    onSuccess: (answer) =>
      setTurns((prior) =>
        prior.map((turn, i) => (i === prior.length - 1 ? { ...turn, answer } : turn)),
      ),
    onError: (error) =>
      setTurns((prior) =>
        prior.map((turn, i) =>
          i === prior.length - 1
            ? {
                ...turn,
                error:
                  error instanceof ApiError
                    ? error.message
                    : "The assistant could not answer that.",
              }
            : turn,
        ),
      ),
  });

  // A question arriving via the URL (from a record page's "Ask AI") should be
  // asked, not merely typed into the box.
  const askedInitial = useRef(false);
  useEffect(() => {
    if (initialQuestion && !askedInitial.current) {
      askedInitial.current = true;
      ask.mutate(initialQuestion);
      setQuestion("");
    }
  }, [initialQuestion, ask]);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight });
  }, [turns]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3 || ask.isPending) return;
    ask.mutate(trimmed);
    setQuestion("");
  }

  return (
    <Card className="flex h-[min(70vh,44rem)] flex-col">
      <div ref={transcript} className="flex-1 space-y-5 overflow-y-auto p-5">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <Sparkles className="size-7 text-sand-300" aria-hidden />
            <div>
              <p className="text-sm font-medium text-navy-900">
                Ask about the records you can access
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-sand-500">
                Answers come from the database and cite the records behind them.
                The assistant is checked against your permissions before it
                retrieves anything.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => ask.mutate(suggestion)}
                  className="rounded-card border border-sand-200 bg-white px-3 py-1.5 text-xs text-navy-800 hover:border-navy-300"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn, index) => (
            <div key={`${turn.question}-${index}`} className="space-y-3">
              <p className="ml-auto max-w-[85%] rounded-card bg-navy-800 px-3.5 py-2 text-sm text-white">
                {turn.question}
              </p>

              {turn.error ? (
                <p className="max-w-[90%] rounded-card border border-low/30 bg-low-bg px-3.5 py-2 text-sm text-low">
                  {turn.error}
                </p>
              ) : turn.answer ? (
                <AnswerBlock answer={turn.answer} />
              ) : (
                <p className="text-sm text-sand-500">Looking that up…</p>
              )}
            </div>
          ))
        )}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-sand-200 p-3">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={placeholder}
          aria-label="Your question"
        />
        <Button type="submit" busy={ask.isPending} disabled={question.trim().length < 3}>
          <CornerDownLeft aria-hidden />
          Ask
        </Button>
      </form>
    </Card>
  );
}

function AnswerBlock({ answer }: { answer: AiAnswer }) {
  return (
    <div className="max-w-[90%] space-y-3">
      <div className="rounded-card border border-sand-200 bg-white px-3.5 py-3">
        <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">
          {answer.answer}
        </p>
      </div>

      {answer.degraded || !answer.llm_used ? (
        <p className="flex items-start gap-2 rounded-card border border-medium/30 bg-medium-bg px-3 py-2 text-xs text-medium">
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
          No language model was available, so this is the database result on its
          own — accurate, but not rephrased.
        </p>
      ) : null}

      {answer.citations.length > 0 ? (
        <div>
          <p className="eyebrow flex items-center gap-1.5">
            <Database className="size-3" aria-hidden />
            Answered from
          </p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {answer.citations.map((citation) => (
              <li
                key={`${citation.type}-${citation.id}`}
                className={cn(
                  "inline-flex items-baseline gap-1.5 rounded-chip border border-sand-200",
                  "bg-sand-50 px-2 py-1 text-xs",
                )}
              >
                <span className="eyebrow">{citation.type}</span>
                <span className="id text-sand-700">{citation.id}</span>
                {citation.detail ? (
                  <span className="record-text text-sand-500">{citation.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-sand-500">
          No records matched that question, so there is nothing to cite.
        </p>
      )}
    </div>
  );
}
