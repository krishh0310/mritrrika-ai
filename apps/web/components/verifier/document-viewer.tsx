"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Maximize2, Minus, Plus, RotateCw, ScanEye } from "lucide-react";

import type { ExtractionField, OcrBlock } from "@/lib/queries";
import { Button, bandFor, cn } from "@mrittika/ui";

/**
 * The left half of the verification workspace (§28).
 *
 * The interaction §28 asks for runs both ways:
 *
 *     click a field  → highlight its bbox and zoom the scan to it
 *     click a bbox   → focus the corresponding field
 *
 * so the viewer takes `selectedField` as a prop and reports clicks upward
 * rather than owning the selection. Both halves read one piece of state, which
 * is what stops them disagreeing about what is selected.
 *
 * Boxes are drawn in an SVG overlay in ORIGINAL page coordinates via a
 * viewBox. That means no coordinate maths anywhere: zoom and pan scale the
 * image and the overlay together, and a box cannot drift off its word.
 */

const ZOOM_STEPS = [0.5, 0.75, 1, 1.5, 2, 3, 4];

export function DocumentViewer({
  imageUrl,
  pageWidth,
  pageHeight,
  fields,
  ocrBlocks,
  selectedField,
  onSelectField,
  className,
}: {
  imageUrl: string | null;
  pageWidth: number | null;
  pageHeight: number | null;
  fields: ExtractionField[];
  ocrBlocks: OcrBlock[];
  selectedField: string | null;
  onSelectField: (extractionId: string) => void;
  className?: string;
}) {
  const [zoomIndex, setZoomIndex] = useState(2); // 1x
  const [rotation, setRotation] = useState(0);
  const [showOcr, setShowOcr] = useState(false);
  const [heatmap, setHeatmap] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);

  const zoom = ZOOM_STEPS[zoomIndex];
  const width = pageWidth ?? 1000;
  const height = pageHeight ?? 1400;

  // Bring the selected field's box into view. Called on selection change from
  // either side, which is what makes "click a field, the document moves" work.
  const scrollToField = useCallback(
    (field: ExtractionField) => {
      const container = scroller.current;
      if (!container) return;
      const [x1, y1, x2, y2] = field.bbox;
      const centreX = ((x1 + x2) / 2 / width) * width * zoom;
      const centreY = ((y1 + y2) / 2 / height) * height * zoom;
      container.scrollTo({
        left: centreX - container.clientWidth / 2,
        top: centreY - container.clientHeight / 2,
        behavior: "smooth",
      });
    },
    [width, height, zoom],
  );

  useEffect(() => {
    const field = fields.find((f) => f.extraction_id === selectedField);
    if (field) scrollToField(field);
  }, [selectedField, fields, scrollToField]);

  // SVG `fill`/`stroke` cannot take a Tailwind class, so the band colours are
  // repeated here as literals. They must stay in step with the --color-high /
  // --color-medium / --color-low tokens in globals.css, which were chosen to
  // pass a colour-vision check rather than by eye.
  function bandColour(score: number | null) {
    const band = bandFor(score);
    if (band === "HIGH") return "#14663d";
    if (band === "MEDIUM") return "#c4841a";
    if (band === "LOW") return "#a61d18";
    return "#8b8272";
  }

  return (
    <div className={cn("flex flex-col overflow-hidden rounded-card border border-sand-200 bg-white", className)}>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-sand-200 bg-sand-50 px-3 py-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
          disabled={zoomIndex === 0}
          aria-label="Zoom out"
        >
          <Minus aria-hidden />
        </Button>
        <span className="id w-12 text-center text-xs text-sand-700">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))}
          disabled={zoomIndex === ZOOM_STEPS.length - 1}
          aria-label="Zoom in"
        >
          <Plus aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setZoomIndex(2)}
          aria-label="Reset zoom"
        >
          <Maximize2 aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setRotation((r) => (r + 90) % 360)}
          aria-label="Rotate"
        >
          <RotateCw aria-hidden />
        </Button>

        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={heatmap ? "outline" : "ghost"}
            size="sm"
            onClick={() => setHeatmap((v) => !v)}
            aria-pressed={heatmap}
          >
            <ScanEye aria-hidden />
            Confidence
          </Button>
          <Button
            variant={showOcr ? "outline" : "ghost"}
            size="sm"
            onClick={() => setShowOcr((v) => !v)}
            aria-pressed={showOcr}
          >
            All text
          </Button>
        </div>
      </div>

      <div ref={scroller} className="relative flex-1 overflow-auto bg-sand-100 p-4">
        <div
          className="relative mx-auto origin-top-left"
          style={{
            width: width * zoom,
            height: height * zoom,
            transform: `rotate(${rotation}deg)`,
          }}
        >
          {imageUrl ? (
            <img
              src={imageUrl}
              alt="Scanned land record"
              width={width}
              height={height}
              className="absolute inset-0 h-full w-full object-contain"
              draggable={false}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-white text-sm text-sand-500">
              The scan could not be loaded. Field boxes are still positioned
              correctly below.
            </div>
          )}

          {/* Original page coordinates. Zoom scales the SVG, not the numbers. */}
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="absolute inset-0 h-full w-full"
            aria-hidden
          >
            {showOcr
              ? ocrBlocks.map((block, index) => {
                  const [x1, y1, x2, y2] = block.bbox;
                  return (
                    <rect
                      key={`ocr-${index}`}
                      x={x1}
                      y={y1}
                      width={x2 - x1}
                      height={y2 - y1}
                      fill="none"
                      stroke="#93aac4"
                      strokeWidth={1}
                      strokeDasharray="3 3"
                    />
                  );
                })
              : null}

            {fields.map((field) => {
              const [x1, y1, x2, y2] = field.bbox;
              const active = field.extraction_id === selectedField;
              const colour = heatmap
                ? bandColour(field.final_confidence)
                : "#1e3a5f";
              return (
                <g key={field.extraction_id}>
                  <rect
                    x={x1}
                    y={y1}
                    width={x2 - x1}
                    height={y2 - y1}
                    fill={colour}
                    fillOpacity={active ? 0.22 : 0.09}
                    stroke={colour}
                    strokeWidth={active ? 3 : 1.5}
                    className="pointer-events-auto cursor-pointer"
                    onClick={() => onSelectField(field.extraction_id)}
                  >
                    <title>
                      {field.field}: {field.effective_value ?? "—"}
                    </title>
                  </rect>
                  {active ? (
                    <text
                      x={x1}
                      y={Math.max(y1 - 6, 12)}
                      fill={colour}
                      fontSize={Math.max(12, height / 90)}
                      fontWeight={600}
                    >
                      {field.field}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      <p className="border-t border-sand-200 bg-sand-50 px-3 py-1.5 text-xs text-sand-500">
        Boxes are coloured by confidence. Click one to jump to its field.
      </p>
    </div>
  );
}
