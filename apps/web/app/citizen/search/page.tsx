"use client";

import { useState } from "react";
import { Search as SearchIcon } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { useLocations, useRecordSearch, type SearchFilters } from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, Field, Input, RecordText, Select, SyntheticNotice, Table, Td, Th, useT,
} from "@mrittika/ui";

/**
 * §17 — public record search.
 *
 * The API returns approved, publicly accessible records only, and strips raw
 * OCR, confidence, verification notes and anomaly scores before they leave the
 * server. This page therefore has nothing to hide: it renders what it is given.
 */
export default function CitizenSearchPage() {
  const t = useT();
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
        title={t("citizen.search.title")}
        description={t("citizen.search.description")}
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
            <Field label={t("citizen.search.villageLabel")}>
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

            <Field label={t("citizen.search.khasraLabel")}>
              <Input
                value={draft.khasra ?? ""}
                onChange={(e) => update("khasra", e.target.value)}
                placeholder="142/2"
              />
            </Field>

            <Field label={t("citizen.search.khataLabel")}>
              <Input
                value={draft.khata ?? ""}
                onChange={(e) => update("khata", e.target.value)}
                placeholder="87"
              />
            </Field>

            <Field label={t("citizen.search.parcelLabel")}>
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
            title={t("citizen.search.resultsTitle")}
            description={
              results.data ? `${results.data.count} matching records` : undefined
            }
            action={<SyntheticNotice />}
          />
          <QueryBoundary
            query={results}
            label={t("citizen.search.loadLabel")}
            empty={{
              when: (data) => data.results.length === 0,
              node: (
                <EmptyState
                  title={t("citizen.search.emptyTitle")}
                  description={t("citizen.search.emptyBody")}
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
                      <Td className="font-medium text-navy-900">
                        <RecordText value={record.khasra_number} />
                      </Td>
                      <Td className="id text-sand-700">{record.khata_number ?? "—"}</Td>
                      <Td>
                        <RecordText value={record.village} stacked />
                      </Td>
                      <Td>
                        <span className="id">{record.area_value}</span>{" "}
                        <span className="text-xs text-sand-500">{record.area_unit}</span>
                      </Td>
                      <Td className="text-sand-700">
                        <RecordText value={record.land_class} stacked />
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
