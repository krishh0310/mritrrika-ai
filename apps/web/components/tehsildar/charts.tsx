"use client";

import {
  Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { cn } from "@mrittika/ui";

/**
 * The analytics charts (§31).
 *
 * Every chart here is ONE series. That is a deliberate choice, not a
 * limitation: "documents per workflow state" compares magnitudes across
 * categories, and the categories live on the axis. Colouring each bar
 * differently would encode nothing — it would just be decoration, and with
 * twelve states it would need twelve hues no reader could tell apart.
 *
 * So: one hue per chart, no legend (the title names the series), horizontal
 * bars because the category labels are long, and the value printed at the end
 * of each bar so nobody has to read a number off a gridline. The only chart
 * that uses more than one colour is the confidence split, where the colours
 * are the reserved status palette and each segment carries its own label.
 */

export const NAVY = "#1e3a5f";
export const BURNT = "#d2691e";

/** Validated against a white surface; see the note in globals.css. */
export const BAND_COLOURS = {
  HIGH: "#14663d",
  MEDIUM: "#c4841a",
  LOW: "#a61d18",
} as const;

const AXIS = { fontSize: 11, fill: "#8b8272" };

function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-card border border-sand-200 bg-white px-2.5 py-1.5 shadow-raised">
      <p className="text-xs font-medium text-navy-900">{label}</p>
      <p className="id text-xs text-sand-700">
        {payload[0].value} {unit}
      </p>
    </div>
  );
}

export type Datum = { name: string; value: number };

/**
 * Horizontal bars, one series.
 *
 * Sorted by value so the reader's eye lands on the biggest first — the
 * alphabetical order the API returns carries no meaning here.
 */
export function CountBars({
  data,
  colour = NAVY,
  unit = "documents",
  suffix = "",
  height,
  className,
}: {
  data: Datum[];
  colour?: string;
  unit?: string;
  /** Printed after each bar's value, e.g. "%" -- a bare number is ambiguous. */
  suffix?: string;
  height?: number;
  className?: string;
}) {
  const sorted = [...data].sort((a, b) => b.value - a.value);
  // 30px a row keeps the bars thin and the labels off each other.
  const computed = height ?? Math.max(120, sorted.length * 30 + 16);

  if (sorted.length === 0) {
    return (
      <p className={cn("px-5 py-8 text-center text-sm text-sand-500", className)}>
        Nothing recorded yet.
      </p>
    );
  }

  return (
    <div className={className} style={{ height: computed }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={sorted}
          layout="vertical"
          margin={{ top: 4, right: 44, bottom: 4, left: 4 }}
          barCategoryGap={6}
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={168}
            tickLine={false}
            axisLine={false}
            tick={AXIS}
          />
          <Tooltip
            cursor={{ fill: "#f0ece1", fillOpacity: 0.6 }}
            content={<ChartTooltip unit={unit} />}
          />
          <Bar dataKey="value" fill={colour} radius={[0, 4, 4, 0]} maxBarSize={16}>
            <LabelList
              dataKey="value"
              position="right"
              formatter={(value: unknown) => `${value}${suffix}`}
              className="id"
              fill="#4f4a40"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * The confidence split (§8), as one stacked bar.
 *
 * A stacked bar rather than three separate ones because these three ARE a
 * whole: every scored field is in exactly one band. Each segment is labelled,
 * so the reserved status colours are never the only signal (§86).
 */
export function ConfidenceSplit({
  bands,
}: {
  bands: { HIGH: number; MEDIUM: number; LOW: number };
}) {
  const total = bands.HIGH + bands.MEDIUM + bands.LOW;

  if (total === 0) {
    return (
      <p className="px-5 py-8 text-center text-sm text-sand-500">
        No fields have been scored yet.
      </p>
    );
  }

  const segments = [
    { key: "HIGH", label: "High", hint: "0.85 and above", count: bands.HIGH },
    { key: "MEDIUM", label: "Medium", hint: "0.60 to 0.85", count: bands.MEDIUM },
    { key: "LOW", label: "Low", hint: "below 0.60", count: bands.LOW },
  ] as const;

  return (
    <div className="p-5">
      {/* 2px gaps between fills, per the mark spec — the bar is a flex row so
          the segments cannot touch. */}
      <div className="flex h-8 gap-0.5 overflow-hidden rounded-chip" role="img"
        aria-label={segments
          .map((s) => `${s.label}: ${s.count} fields`)
          .join(", ")}
      >
        {segments
          .filter((segment) => segment.count > 0)
          .map((segment) => (
            <div
              key={segment.key}
              style={{
                width: `${(segment.count / total) * 100}%`,
                background: BAND_COLOURS[segment.key],
              }}
              className="first:rounded-l-chip last:rounded-r-chip"
            />
          ))}
      </div>

      <dl className="mt-4 space-y-2.5">
        {segments.map((segment) => (
          <div key={segment.key} className="flex items-baseline gap-2.5">
            <span
              aria-hidden
              className="size-2.5 shrink-0 translate-y-px rounded-[2px]"
              style={{ background: BAND_COLOURS[segment.key] }}
            />
            <dt className="text-sm text-navy-900">
              {segment.label}
              <span className="ml-1.5 text-xs text-sand-500">{segment.hint}</span>
            </dt>
            <dd className="id ml-auto text-sm text-sand-700">
              {segment.count}
              <span className="ml-1.5 text-xs text-sand-500">
                {Math.round((segment.count / total) * 100)}%
              </span>
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 border-t border-sand-100 pt-3 text-xs text-sand-500">
        <span className="id">{total}</span> extracted fields scored in total.
      </p>
    </div>
  );
}

/** Turn an API histogram into chart rows, in the interface's own wording. */
export function toData(
  counts: Record<string, number>,
  prettify: (key: string) => string = (k) => k.replaceAll("_", " ").toLowerCase(),
): Datum[] {
  return Object.entries(counts).map(([name, value]) => ({
    name: prettify(name),
    value,
  }));
}

export { Cell };
