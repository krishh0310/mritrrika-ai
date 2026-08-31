"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { FileUp, UploadCloud } from "lucide-react";

import { PageHeader } from "@/components/shell/app-shell";
import { ApiError, api } from "@/lib/api-client";
import { useLocations, type DocumentSummary } from "@/lib/queries";
import {
  Button, Card, CardHeader, Field, Input, Select, cn,
} from "@mrittika/ui";

/**
 * §21 — capture a scan plus the metadata only a human knows.
 *
 * The accepted types are echoed from the server's own list rather than being
 * enforced here: the API decides by sniffing the bytes (§61), so a check in
 * this form is a courtesy to the operator, never the gate.
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

export default function DeoUploadPage() {
  const router = useRouter();
  const villages = useLocations("VILLAGE");
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [documentType, setDocumentType] = useState("KHASRA");
  const [villageId, setVillageId] = useState("");
  const [recordYear, setRecordYear] = useState("");
  const [khasra, setKhasra] = useState("");
  const [khata, setKhata] = useState("");
  const [parcelId, setParcelId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a file first");
      const form = new FormData();
      form.set("file", file);
      form.set("document_type", documentType);
      if (villageId) form.set("village_id", villageId);
      if (recordYear) form.set("record_year", recordYear);
      if (khasra) form.set("khasra_number", khasra);
      if (khata) form.set("khata_number", khata);
      if (parcelId) form.set("parcel_id", parcelId);
      return api.upload<DocumentSummary>("/api/v1/documents", form);
    },
    onSuccess: (document) => router.push(`/deo/documents/${document.document_id}`),
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "The upload failed.",
      ),
  });

  return (
    <>
      <PageHeader
        title="Upload a document"
        description="The scan goes through a quality check the moment it arrives, before any model runs."
      />

      <form
        className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          upload.mutate();
        }}
      >
        <Card>
          <CardHeader title="The scan" />
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
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) setFile(dropped);
              }}
              className={cn(
                "flex flex-col items-center gap-3 rounded-card border-2 border-dashed p-10 text-center",
                dragging ? "border-burnt bg-cream" : "border-sand-200 bg-sand-50",
              )}
            >
              <UploadCloud
                className={cn("size-8", dragging ? "text-burnt" : "text-sand-300")}
                aria-hidden
              />
              {file ? (
                <div>
                  <p className="text-sm font-medium text-navy-900">{file.name}</p>
                  <p className="id mt-0.5 text-xs text-sand-500">
                    {(file.size / 1024).toFixed(0)} KB
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-sm font-medium text-navy-900">
                    Drop a scan here, or choose a file
                  </p>
                  <p className="mt-0.5 text-xs text-sand-500">
                    PDF, PNG or JPEG. One page per upload.
                  </p>
                </div>
              )}

              <input
                ref={fileInput}
                type="file"
                accept={ACCEPTED}
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileInput.current?.click()}
              >
                <FileUp aria-hidden />
                {file ? "Choose a different file" : "Choose a file"}
              </Button>
            </div>

            {error ? (
              <p
                role="alert"
                className="mt-4 rounded-card border border-low/30 bg-low-bg px-3 py-2 text-sm text-low"
              >
                {error}
              </p>
            ) : null}
          </div>
        </Card>

        <Card className="self-start">
          <CardHeader
            title="What is on it"
            description="Kept separate from anything the AI later reads off the page."
          />
          <div className="space-y-4 p-5">
            <Field label="Document type" required>
              <Select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
                required
              >
                {DOCUMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replaceAll("_", " ")}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Village">
              <Select value={villageId} onChange={(e) => setVillageId(e.target.value)}>
                <option value="">Not recorded</option>
                {(villages.data?.locations ?? []).map((location) => (
                  <option key={location.location_id} value={location.location_id}>
                    {location.name_devanagari ?? location.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Record year" hint="As written on the page, e.g. 1998-99.">
              <Input
                className="id"
                value={recordYear}
                onChange={(e) => setRecordYear(e.target.value)}
                placeholder="1998-99"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Khasra">
                <Input
                  className="id"
                  value={khasra}
                  onChange={(e) => setKhasra(e.target.value)}
                  placeholder="142/2"
                />
              </Field>
              <Field label="Khata">
                <Input
                  className="id"
                  value={khata}
                  onChange={(e) => setKhata(e.target.value)}
                  placeholder="87"
                />
              </Field>
            </div>

            <Field
              label="Link to parcel"
              hint="Links the record to the cadastre, so history and anomaly checks can run."
            >
              <Input
                className="id"
                value={parcelId}
                onChange={(e) => setParcelId(e.target.value)}
                placeholder="PARCEL-UP-DEMO-0142"
              />
            </Field>

            <Button
              type="submit"
              busy={upload.isPending}
              disabled={!file}
              className="w-full"
              size="lg"
            >
              Upload and check quality
            </Button>
          </div>
        </Card>
      </form>
    </>
  );
}
