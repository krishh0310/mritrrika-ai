import { Layers, MapPin, Ruler } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "./cn";

/**
 * One holding, as a card (§15).
 *
 * parcel_id leads and is set in the identifier face, because §11 makes it the
 * join key of the whole system — it is the thing a citizen quotes at a counter
 * and an officer searches on. Devanagari values (village, land class) are set
 * in the record face so they match the document they came from.
 */

export type ParcelSummary = {
  parcel_id: string;
  khasra_number: string;
  khata_number?: string | null;
  village?: string | null;
  area_value: number;
  area_unit: string;
  area_unit_raw?: string | null;
  land_class?: string | null;
  share?: string | null;
};

export function ParcelCard({
  parcel,
  actions,
  selected,
  onSelect,
  className,
}: {
  parcel: ParcelSummary;
  actions?: ReactNode;
  selected?: boolean;
  onSelect?: () => void;
  className?: string;
}) {
  const Wrapper = onSelect ? "button" : "div";

  return (
    <Wrapper
      type={onSelect ? "button" : undefined}
      onClick={onSelect}
      className={cn(
        "block w-full rounded-card border bg-white text-left shadow-panel",
        "transition-colors",
        selected ? "border-burnt ring-1 ring-burnt" : "border-sand-200",
        onSelect && "hover:border-navy-300",
        className,
      )}
    >
      <div className="border-b border-sand-100 px-4 py-3">
        <p className="eyebrow">Khasra</p>
        <p className="record-text mt-0.5 text-xl leading-tight font-semibold text-navy-900">
          {parcel.khasra_number}
        </p>
        <p className="id mt-1.5 text-xs text-sand-500">{parcel.parcel_id}</p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 px-4 py-3 text-sm">
        {parcel.village ? (
          <div className="col-span-2">
            <dt className="eyebrow flex items-center gap-1">
              <MapPin className="size-3" aria-hidden />
              Village
            </dt>
            <dd className="record-text mt-0.5 text-navy-900">{parcel.village}</dd>
          </div>
        ) : null}

        <div>
          <dt className="eyebrow flex items-center gap-1">
            <Ruler className="size-3" aria-hidden />
            Area
          </dt>
          <dd className="mt-0.5">
            <span className="id text-navy-900">{parcel.area_value}</span>{" "}
            <span className="record-text text-sand-700">
              {parcel.area_unit_raw ?? parcel.area_unit}
            </span>
          </dd>
        </div>

        {parcel.share ? (
          <div>
            <dt className="eyebrow">Your share</dt>
            <dd className="id mt-0.5 text-navy-900">{parcel.share}</dd>
          </div>
        ) : null}

        {parcel.land_class ? (
          <div>
            <dt className="eyebrow flex items-center gap-1">
              <Layers className="size-3" aria-hidden />
              Class
            </dt>
            <dd className="record-text mt-0.5 text-sand-700">{parcel.land_class}</dd>
          </div>
        ) : null}

        {parcel.khata_number ? (
          <div>
            <dt className="eyebrow">Khata</dt>
            <dd className="id mt-0.5 text-sand-700">{parcel.khata_number}</dd>
          </div>
        ) : null}
      </dl>

      {actions ? (
        <div className="flex flex-wrap gap-2 border-t border-sand-100 px-4 py-2.5">{actions}</div>
      ) : null}
    </Wrapper>
  );
}
