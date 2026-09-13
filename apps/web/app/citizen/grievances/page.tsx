"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Paperclip, Send } from "lucide-react";

import { QueryBoundary } from "@/components/shared/query-boundary";
import { PageHeader } from "@/components/shell/app-shell";
import { ApiError, api } from "@/lib/api-client";
import { useIssueTypes, useMyGrievances, useMyParcels } from "@/lib/queries";
import {
  Button, Card, CardHeader, EmptyState, Field, GrievanceStatus, Input, LoadingState, Select, Table, Td, Textarea, Th, useT,
} from "@mrittika/ui";

/** Issue types come from the API; these are the words a citizen reads. */
const ISSUE_LABELS: Record<string, string> = {
  INCORRECT_OWNER_NAME: "The owner name is wrong",
  INCORRECT_AREA: "The recorded area is wrong",
  INCORRECT_KHASRA: "The khasra number is wrong",
  MISSING_MUTATION: "A mutation is missing",
  BOUNDARY_DISPUTE: "The boundary is disputed",
  DOCUMENT_NOT_FOUND: "I cannot find a record",
  OTHER: "Something else",
};

function GrievancesScreen() {
  const t = useT();
  const preselected = useSearchParams().get("parcel") ?? "";
  const queryClient = useQueryClient();

  const mine = useMyGrievances();
  const parcels = useMyParcels();
  const issueTypes = useIssueTypes();

  const [parcelId, setParcelId] = useState(preselected);
  const [issueType, setIssueType] = useState("INCORRECT_AREA");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      form.set("issue_type", issueType);
      form.set("description", description.trim());
      if (parcelId) form.set("parcel_id", parcelId);
      if (file) form.set("supporting_document", file);
      return api.upload("/api/v1/grievances", form);
    },
    onSuccess: () => {
      setDescription("");
      setFile(null);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["grievances", "me"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The grievance could not be filed. Try again.",
      ),
  });

  return (
    <>
      <PageHeader
        title={t("citizen.grievances.title")}
        description={t("citizen.grievances.description")}
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader title={t("citizen.grievances.raiseTitle")} />
          <form
            className="space-y-4 p-5"
            onSubmit={(event) => {
              event.preventDefault();
              submit.mutate();
            }}
          >
            <Field
              label={t("citizen.grievances.whichParcel")}
              hint="Leave blank if the issue is not about one of your parcels."
            >
              <Select value={parcelId} onChange={(e) => setParcelId(e.target.value)}>
                <option value="">Not about a specific parcel</option>
                {(parcels.data?.parcels ?? []).map((parcel) => (
                  <option key={parcel.parcel_id} value={parcel.parcel_id}>
                    Khasra {parcel.khasra_number} — {parcel.village}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label={t("citizen.grievances.whatIsWrong")} required>
              <Select
                value={issueType}
                onChange={(e) => setIssueType(e.target.value)}
                required
              >
                {(issueTypes.data?.issue_types ?? Object.keys(ISSUE_LABELS)).map(
                  (type) => (
                    <option key={type} value={type}>
                      {ISSUE_LABELS[type] ?? type}
                    </option>
                  ),
                )}
              </Select>
            </Field>

            <Field
              label={t("citizen.grievances.describe")}
              required
              hint="Say what the record shows and what it should show."
            >
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                maxLength={4000}
                placeholder="The area on khasra 142/2 is recorded as 27 bigha. The 1998 record shows 2.7 bigha."
              />
            </Field>

            <Field
              label={t("citizen.grievances.attachment")}
              hint="Optional. PDF, PNG or JPEG."
            >
              <Input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm file:mr-3 file:rounded file:border-0 file:bg-sand-100 file:px-2 file:py-1 file:text-xs"
              />
              {file ? (
                <span className="mt-1.5 flex items-center gap-1.5 text-xs text-sand-500">
                  <Paperclip className="size-3" aria-hidden />
                  {file.name}
                </span>
              ) : null}
            </Field>

            {error ? (
              <p role="alert" className="rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low">
                {error}
              </p>
            ) : null}

            {submit.isSuccess && !error ? (
              <p role="status" className="rounded-card border border-high/30 bg-high-bg px-3 py-2 text-sm text-high">
                Filed. You can follow it in the list beside this form.
              </p>
            ) : null}

            <Button
              type="submit"
              busy={submit.isPending}
              disabled={description.trim().length === 0}
              className="w-full"
            >
              <Send aria-hidden />
              File grievance
            </Button>
          </form>
        </Card>

        <Card>
          <CardHeader
            title={t("citizen.grievances.yoursTitle")}
            description={mine.data ? `${mine.data.count} filed` : undefined}
          />
          <QueryBoundary
            query={mine}
            label={t("citizen.grievances.loadLabel")}
            empty={{
              when: (data) => data.grievances.length === 0,
              node: (
                <EmptyState
                  title={t("citizen.grievances.emptyTitle")}
                  description={t("citizen.grievances.emptyBody")}
                />
              ),
            }}
          >
            {(data) => (
              <Table>
                <thead>
                  <tr>
                    <Th>Reference</Th>
                    <Th>Issue</Th>
                    <Th>Parcel</Th>
                    <Th>Status</Th>
                    <Th>Filed</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.grievances.map((grievance) => (
                    <tr key={grievance.grievance_id} className="align-top">
                      <Td className="id text-sand-700">{grievance.grievance_id}</Td>
                      <Td>
                        <p className="text-navy-900">
                          {ISSUE_LABELS[grievance.issue_type] ?? grievance.issue_type}
                        </p>
                        <p className="mt-0.5 max-w-md text-xs text-sand-500">
                          {grievance.description}
                        </p>
                        {grievance.resolution_note ? (
                          <p className="mt-1.5 rounded-chip bg-sand-50 px-2 py-1 text-xs text-sand-700">
                            <span className="eyebrow mr-1.5">Officer</span>
                            {grievance.resolution_note}
                          </p>
                        ) : null}
                      </Td>
                      <Td className="record-text">
                        {grievance.khasra_number ?? "—"}
                      </Td>
                      <Td>
                        <GrievanceStatus status={grievance.status} />
                      </Td>
                      <Td className="id text-xs text-sand-500">
                        {grievance.created_at?.slice(0, 10) ?? "—"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </QueryBoundary>
        </Card>
      </div>
    </>
  );
}

export default function CitizenGrievancesPage() {
  const t = useT();
  return (
    <Suspense fallback={<LoadingState label={t("citizen.grievances.loadLabel")} />}>
      <GrievancesScreen />
    </Suspense>
  );
}
