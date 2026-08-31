"use client";

import { useState } from "react";
import { Search as SearchIcon } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useLocations, useRecordSearch, type SearchFilters } from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, Field, Input, Select, SyntheticNotice,
  Table, Td, Th,
} from "@mrittika/ui";

/**
 * §17 — public record search.
 *
 * The API returns approved, publicly accessible records only, and strips raw
 * OCR, confidence, verification notes and anomaly scores before they leave the
 * server. This page therefore has nothing to hide: it renders what it is given.
 */
export default function CitizenSearchPage() {
  const [draft, setDraft] = useState<SearchFilters>({});
  const [submitted, setSubmitted] = useState<SearchFilters | null>(null);

  const villages = useLocations("VILLAGE");
  const results = useRecordSearch(submitted ?? {}, submitted !== null);

  function update(key: keyof SearchFilters, value: string) {
    setDraft((current) => ({ ...current, [key]: value || undefined }));
  }

  return (
    <>
      <PageHeader
        title="Search records"
        description="Approved public land records. Search by location, khasra, khata or parcel identifier."
      />

      <Card>
        <form
          className="p-5"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(draft);
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Village">
              <Select
                value={draft.village_id ?? ""}
                onChange={(e) => update("village_id", e.target.value)}
              >
                <option value="">Any village</option>
                {(villages.data?.locations ?? []).map((location) => (
                  <option key={location.location_id} value={location.location_id}>
                    {location.name_devanagari ?? location.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Khasra number">
              <Input
                value={draft.khasra ?? ""}
                onChange={(e) => update("khasra", e.target.value)}
                placeholder="142/2"
              />
            </Field>

            <Field label="Khata number">
              <Input
                value={draft.khata ?? ""}
                onChange={(e) => update("khata", e.target.value)}
                placeholder="87"
              />
            </Field>

            <Field label="Parcel identifier">
              <Input
                className="id"
                value={draft.parcel_id ?? ""}
                onChange={(e) => update("parcel_id", e.target.value)}
                placeholder="PARCEL-UP-DEMO-0142"
              />
            </Field>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <Button type="submit" busy={results.isFetching && submitted !== null}>
              <SearchIcon aria-hidden />
              Search
            </Button>
            {submitted ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraft({});
                  setSubmitted(null);
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>
        </form>
      </Card>

      {submitted ? (
        <Card className="mt-5">
          <CardHeader
            title="Results"
            description={
              results.data ? `${results.data.count} matching records` : undefined
            }
            action={<SyntheticNotice />}
          />
          <QueryBoundary
            query={results}
            label="search results"
            empty={{
              when: (data) => data.results.length === 0,
              node: (
                <EmptyState
                  title="No approved records match those filters"
                  description="Try a broader search — a village on its own, or just the khasra number."
                />
              ),
            }}
          >
            {(data) => (
              <Table>
                <thead>
                  <tr>
                    <Th>Khasra</Th>
                    <Th>Khata</Th>
                    <Th>Village</Th>
                    <Th>Area</Th>
                    <Th>Classification</Th>
                    <Th>Parcel</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((record) => (
                    <tr key={record.parcel_id} className="hover:bg-sand-50">
                      <Td className="record-text font-medium text-navy-900">
                        {record.khasra_number}
                      </Td>
                      <Td className="id text-sand-700">{record.khata_number ?? "—"}</Td>
                      <Td className="record-text">{record.village ?? "—"}</Td>
                      <Td>
                        <span className="id">{record.area_value}</span>{" "}
                        <span className="text-xs text-sand-500">{record.area_unit}</span>
                      </Td>
                      <Td className="record-text text-sand-700">
                        {record.land_class ?? "—"}
                      </Td>
                      <Td className="id text-xs text-sand-500">{record.parcel_id}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </QueryBoundary>
        </Card>
      ) : (
        <Card className="mt-5">
          <EmptyState
            icon={<SearchIcon className="size-7" aria-hidden />}
            title="Set a filter and search"
            description="Public search covers approved records only. Nothing still in verification appears here."
          />
        </Card>
      )}
    </>
  );
}
