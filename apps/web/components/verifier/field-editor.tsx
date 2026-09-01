"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Pencil, RotateCcw } from "lucide-react";

import type { FieldStatus } from "@mrittika/shared-types";

import type { ExtractionField, ValidationFinding } from "@/lib/queries";
import {
  Button, ConfidenceBadge, Field, Input, ProvenanceCaption, cn,
} from "@mrittika/ui";

/**
 * One extracted field, editable (§28 right pane).
 *
 * The rule this component exists to make visible: a correction never
 * overwrites the model's prediction (§26, §30). The raw OCR and the normalized
 * value stay on screen underneath the input, so a verifier can always see what
 * they are changing it from — and so can the tehsildar reviewing them later.
 */

/** The field names the API emits, in the words an officer uses. */
const FIELD_LABELS: Record<string, string> = {
  OWNER: "Owner name",
  GUARDIAN: "Guardian name",
  KHASRA: "Khasra number",
  KHATA: "Khata number",
  VILLAGE: "Village",
  TEHSIL: "Tehsil",
  DISTRICT: "District",
  STATE: "State",
  AREA: "Area",
  AREA_UNIT: "Area unit",
  LAND_CLASS: "Land classification",
  MUTATION: "Mutation number",
  DATE: "Date",
  SHARE: "Share",
  REMARK: "Remark",
};

export function FieldEditor({
  field,
  findings,
  selected,
  onSelect,
  onCorrect,
  onAccept,
  busy,
  readOnly,
}: {
  field: ExtractionField;
  findings: ValidationFinding[];
  selected: boolean;
  onSelect: () => void;
  onCorrect: (value: string, reason?: string) => void;
  onAccept: () => void;
  busy: boolean;
  readOnly?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(field.effective_value ?? "");
  const input = useRef<HTMLInputElement>(null);
  const container = useRef<HTMLDivElement>(null);

  // Selection can come from a click on the document, so this pane has to move
  // to the field rather than assuming the user scrolled here (§28).
  useEffect(() => {
    if (selected) {
      container.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selected]);

  useEffect(() => {
    if (editing) input.current?.focus();
  }, [editing]);

  // A correction from elsewhere (a refetch) must not be masked by a stale draft.
  useEffect(() => {
    if (!editing) setDraft(field.effective_value ?? "");
  }, [field.effective_value, editing]);

  const relevant = findings.filter((f) => f.field === field.field);
  const corrected = Boolean(field.corrected_value);

  // The vocabulary is packages/domain's FieldStatus, generated into
  // shared-types. Typing it against that is what stops this drifting from what
  // the API writes -- an earlier version checked for "ACCEPTED", which the
  // server never emits, so accepting a field changed nothing on screen.
  const status = field.status as FieldStatus;
  const accepted =
    status === "AUTO_ACCEPTED" || status === "VERIFIER_APPROVED";

  return (
    <div
      ref={container}
      onClick={onSelect}
      className={cn(
        "scroll-mt-4 border-l-2 px-4 py-3.5 transition-colors",
        selected ? "border-l-burnt bg-cream/40" : "border-l-transparent hover:bg-sand-50",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-navy-900">
          {FIELD_LABELS[field.field] ?? field.field}
          {field.row_index !== null ? (
            <span className="id ml-1.5 text-xs text-sand-500">
              row {field.row_index + 1}
            </span>
          ) : null}
        </p>
        <div className="flex items-center gap-2">
          {corrected ? (
            <span className="inline-flex items-center gap-1 rounded-chip bg-navy-100 px-1.5 py-0.5 text-[0.6875rem] font-semibold tracking-wider text-navy-800 uppercase">
              <Pencil className="size-2.5" aria-hidden />
              Corrected
            </span>
          ) : accepted ? (
            <span className="inline-flex items-center gap-1 rounded-chip bg-high-bg px-1.5 py-0.5 text-[0.6875rem] font-semibold tracking-wider text-high uppercase">
              <Check className="size-2.5" aria-hidden />
              Accepted
            </span>
          ) : null}
          <ConfidenceBadge score={field.final_confidence} />
        </div>
      </div>

      {editing ? (
        <div className="mt-2 space-y-2">
          <Field label="Corrected value" className="[&>span:first-child]:sr-only">
            <Input
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="record-text text-base"
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setEditing(false);
                  setDraft(field.effective_value ?? "");
                }
                if (e.key === "Enter" && draft.trim()) {
                  onCorrect(draft.trim());
                  setEditing(false);
                }
              }}
            />
          </Field>
          <div className="flex gap-2">
            <Button
              size="sm"
              busy={busy}
              disabled={!draft.trim() || draft.trim() === field.effective_value}
              onClick={() => {
                onCorrect(draft.trim());
                setEditing(false);
              }}
            >
              Save correction
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setDraft(field.effective_value ?? "");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <p className="record-text text-base text-navy-900">
            {field.effective_value || (
              <span className="text-sm text-sand-500 italic">
                nothing was read here
              </span>
            )}
          </p>
          {!readOnly ? (
            <div className="ml-auto flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                <Pencil aria-hidden />
                Correct
              </Button>
              {!accepted && !corrected ? (
                <Button size="sm" variant="ghost" busy={busy} onClick={onAccept}>
                  <Check aria-hidden />
                  Accept
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      <ProvenanceCaption
        className="mt-2"
        raw={field.raw_value}
        normalized={field.normalized_value}
        modelVersion={field.model_version}
      />

      {corrected ? (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-sand-500">
          <RotateCcw className="size-3" aria-hidden />
          The model predicted{" "}
          <span className="record-text text-sand-700">
            {field.normalized_value || "—"}
          </span>
          . That prediction is kept.
        </p>
      ) : null}

      {relevant.map((finding) => (
        <p
          key={finding.rule}
          className={cn(
            "mt-2 flex items-start gap-1.5 rounded-chip px-2 py-1.5 text-xs",
            finding.severity === "error"
              ? "bg-low-bg text-low"
              : "bg-medium-bg text-medium",
          )}
        >
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
          <span>
            {finding.message}
            <span className="id ml-1.5 opacity-70">{finding.rule}</span>
          </span>
        </p>
      ))}
    </div>
  );
}
