"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileUp, UploadCloud } from "lucide-react";

import { PageHeader } from "@/components/shell/app-shell";
import { ApiError, api } from "@/lib/api-client";
import { useLocations } from "@/lib/queries";
import { Button, Card, CardHeader, Field, Input, Select, Table, Td, Th, cn } from "@mrittika/ui";

/**
 * §21 — a tray of scans in one request.
 *
 * Separate from the single-upload screen rather than a mode inside it, because
 * the two ask for different metadata. A single upload carries the khasra and
 * khata numbers only a human reading that page knows; a batch cannot, so it
 * carries only what is true of the whole tray (village, type, record year) and
 * leaves the per-page metadata to be filled in during verification.
 *
 * The result screen is the important part. Partial success is the normal
 * outcome, so the response is rendered as two lists rather than a single
 * success or failure -- an operator needs to see which files landed and
 * exactly why the others did not.
 */

const DOCUMENT_TYPES = [
  "KHASRA",
  "KHATAUNI",
  "JAMABANDI",
  "MUTATION_REGISTER",
  "RECORD_OF_RIGHTS",
  "SUPPORTING",
];

const ACCEPTED = ".pdf,.png,.jpg,.jpeg";
const MAX_FILES = 40;

type Accepted = {
  document_id: string;
  quality_recommendation?: string | null;
};

type Rejected = {
  filename: string;
  code: string;
  reason: string;
  existing_document?: string;
};

type BatchResult = {
  counts: {
    submitted: number;
    accepted: number;
    rejected: number;
    needs_rescan: number;
  };
  accepted: Accepted[];
  rejected: Rejected[];
};

export default function DeoBulkUploadPage() {
  const villages = useLocations("VILLAGE");
  const fileInput = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [documentType, setDocumentType] = useState("KHASRA");
  const [villageId, setVillageId] = useState("");
  const [recordYear, setRecordYear] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchResult | null>(null);

  const upload = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      form.set("document_type", documentType);
      form.set("village_id", villageId);
      if (recordYear) form.set("record_year", recordYear);
      return api.upload<BatchResult>("/api/v1/documents/batch", form);
    },
    onSuccess: (body) => {
      setResult(body);
      setFiles([]);
      if (fileInput.current) fileInput.current.value = "";
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "The batch could not be uploaded.",
      ),
  });

  const tooMany = files.length > MAX_FILES;

  return (
    <>
      <PageHeader
        title="Upload a batch"
        description="Every page goes through the same quality check as a single upload. Files that cannot be stored are listed with the reason; the rest still land."
      />

      <form
        className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          setResult(null);
          upload.mutate();
        }}
      >
        <Card>
          <CardHeader title="The scans" />
          <div className="p-5">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                setFiles(Array.from(e.dataTransfer.files));
              }}
              className={cn(
                "flex flex-col items-center gap-3 rounded-card border-2 border-dashed p-8 text-center",
                dragging ? "border-burnt bg-cream" : "border-sand-300 bg-sand-50",
              )}
            >
              <UploadCloud className="size-8 text-navy-600" aria-hidden />
              <p className="text-sm text-sand-700">
                Drop a tray of scans here, or choose them below.
              </p>
              <input
                ref={fileInput}
                type="file"
                name="files"
                multiple
                accept={ACCEPTED}
                aria-label="Scans"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                className="text-sm"
              />
            </div>

            {files.length > 0 ? (
              <div className="mt-4">
                <p className="text-sm font-medium text-navy-900">
                  {files.length} file{files.length === 1 ? "" : "s"} selected
                </p>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-sm text-sand-700">
                  {files.map((file) => (
                    <li key={file.name} className="flex items-center gap-2">
                      <FileUp className="size-3.5" aria-hidden />
                      {file.name}
                    </li>
                  ))}
                </ul>
                {tooMany ? (
                  <p role="alert" className="mt-3 text-sm text-low">
                    That is more than {MAX_FILES} files. Split the tray and upload
                    again.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader title="What is true of the whole tray" />
          <div className="space-y-4 p-5">
            <Field label="Document type" required>
              <Select
                name="document_type"
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
              >
                {DOCUMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Village" required>
              <Select
                name="village_id"
                value={villageId}
                onChange={(e) => setVillageId(e.target.value)}
              >
                <option value="">Choose a village</option>
                {(villages.data?.locations ?? []).map((location) => (
                  <option key={location.location_id} value={location.location_id}>
                    {location.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Record year">
              <Input
                name="record_year"
                value={recordYear}
                onChange={(e) => setRecordYear(e.target.value)}
                placeholder="1998-99"
              />
            </Field>

            <p className="text-xs leading-relaxed text-sand-500">
              Khasra and khata numbers are not asked for here — they differ per
              page. They are filled in during verification.
            </p>

            {error ? (
              <p role="alert" className="text-sm text-low">
                {error}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={files.length === 0 || !villageId || tooMany || upload.isPending}
            >
              {upload.isPending
                ? `Uploading ${files.length}…`
                : `Upload ${files.length || ""} scan${files.length === 1 ? "" : "s"}`}
            </Button>
          </div>
        </Card>
      </form>

      {result ? <BatchResultPanel result={result} /> : null}
    </>
  );
}

function BatchResultPanel({ result }: { result: BatchResult }) {
  const { counts } = result;
  return (
    <Card className="mt-6">
      <CardHeader
        title="Result"
        description={`${counts.accepted} of ${counts.submitted} stored${
          counts.rejected ? `, ${counts.rejected} not stored` : ""
        }${counts.needs_rescan ? `, ${counts.needs_rescan} need rescanning` : ""}.`}
      />

      {result.accepted.length > 0 ? (
        <div className="p-5 pt-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-navy-900">
            <CheckCircle2 className="size-4 text-high" aria-hidden />
            Stored
          </h3>
          <Table>
            <thead>
              <tr>
                <Th>Document</Th>
                <Th>Quality</Th>
              </tr>
            </thead>
            <tbody>
              {result.accepted.map((row) => (
                <tr key={row.document_id}>
                  <Td>
                    <Link
                      href={`/deo/documents/${row.document_id}`}
                      className="underline underline-offset-4"
                    >
                      {row.document_id}
                    </Link>
                  </Td>
                  <Td>{row.quality_recommendation ?? "—"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      ) : null}

      {result.rejected.length > 0 ? (
        <div className="p-5 pt-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-navy-900">
            <AlertTriangle className="size-4 text-medium" aria-hidden />
            Not stored
          </h3>
          <Table>
            <thead>
              <tr>
                <Th>File</Th>
                <Th>Why</Th>
              </tr>
            </thead>
            <tbody>
              {result.rejected.map((row) => (
                <tr key={row.filename}>
                  <Td>{row.filename}</Td>
                  <Td>
                    {row.reason}
                    {row.existing_document ? (
                      <>
                        {" "}
                        <Link
                          href={`/deo/documents/${row.existing_document}`}
                          className="underline underline-offset-4"
                        >
                          {row.existing_document}
                        </Link>
                      </>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      ) : null}
    </Card>
  );
}
