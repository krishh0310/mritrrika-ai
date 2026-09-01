/**
 * Typed reads of the API, in one place.
 *
 * The mobile counterpart of apps/web/lib/queries.ts, carrying only what §4
 * gives the phone: the citizen portal, capture, and processing status. The
 * response types are copied rather than imported because the two apps have no
 * shared runtime; they must be kept in step with the web file, which is the
 * one the officer screens exercise.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

// ── Shapes the API actually returns ─────────────────────────────────────────

export type Holding = {
  parcel_id: string;
  khasra_number: string;
  khata_number: string | null;
  village: string | null;
  village_id: string | null;
  area_value: number;
  area_unit: string;
  area_unit_raw: string | null;
  land_class: string | null;
  share: string | null;
  held_since: string | null;
  is_synthetic: boolean;
};

export type CitizenDashboard = {
  citizen_name: string;
  parcel_count: number;
  total_area: number;
  area_units: string[];
  is_synthetic: boolean;
};

export type ParcelDetail = {
  parcel_id: string;
  khasra_number: string;
  khata_number: string | null;
  area_value: number;
  area_unit: string;
  area_unit_raw: string | null;
  land_class: string | null;
  is_synthetic: boolean;
};

export type OwnershipSpan = {
  owner: string;
  owner_id: string;
  share: string;
  valid_from: string;
  /** null means "current holder" (§39). */
  valid_to: string | null;
  mutation_number: string | null;
  mutation_type: string | null;
};

export type SearchResult = {
  parcel_id: string;
  khasra_number: string;
  khata_number: string | null;
  village: string | null;
  village_id: string | null;
  area_value: number;
  area_unit: string;
  land_class: string | null;
  is_synthetic: boolean;
};

export type Location = {
  location_id: string;
  name: string;
  name_devanagari: string | null;
  level: string;
};

export type Grievance = {
  grievance_id: string;
  parcel_id: string | null;
  khasra_number: string | null;
  issue_type: string;
  description: string;
  status: string;
  resolution_note: string | null;
  has_attachment: boolean;
  raised_by: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type DocumentSummary = {
  document_id: string;
  document_type: string;
  state: string;
  quality_score: number | null;
  quality_recommendation: string | null;
  original_filename: string | null;
  size_bytes: number | null;
  record_year: string | null;
  declared_khasra: string | null;
  is_synthetic: boolean;
};

export type ProcessingStatus = {
  document_id: string;
  state: string;
  stage: string | null;
  progress: number;
  status: string;
  message: string | null;
  error: string | null;
};

export type AiAnswer = {
  answer: string;
  /** What the answer was built from. §18 forbids an uncited claim. */
  citations: { type: string; id: string; detail: string | null }[];
  records: Record<string, unknown>[];
  intent: string;
  /** False when no LLM was reachable and the structured result stands alone (§82). */
  llm_used: boolean;
  degraded: boolean;
  is_synthetic: boolean;
};

export type ParcelFeatureCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: string; coordinates: number[][][] | number[][][][] };
    properties: Record<string, unknown>;
  }[];
};

// ── Citizen ─────────────────────────────────────────────────────────────────

export function useCitizenDashboard() {
  return useQuery({
    queryKey: ["citizen", "dashboard"],
    queryFn: () => api.get<CitizenDashboard>("/api/v1/citizen/dashboard"),
  });
}

export function useMyParcels() {
  return useQuery({
    queryKey: ["citizen", "parcels"],
    queryFn: () =>
      api.get<{ count: number; parcels: Holding[] }>("/api/v1/citizen/my-parcels"),
  });
}

export function useParcelDetail(parcelId: string) {
  return useQuery({
    queryKey: ["citizen", "parcel", parcelId],
    queryFn: () => api.get<ParcelDetail>(`/api/v1/citizen/parcels/${parcelId}`),
  });
}

export function useOwnershipHistory(parcelId: string) {
  return useQuery({
    queryKey: ["citizen", "history", parcelId],
    queryFn: () =>
      api.get<{ parcel_id: string; history: OwnershipSpan[] }>(
        `/api/v1/citizen/parcels/${parcelId}/ownership-history`,
      ),
  });
}

// ── Search, locations and GIS ───────────────────────────────────────────────

export type SearchFilters = {
  village_id?: string;
  khasra?: string;
  khata?: string;
  parcel_id?: string;
  owner_name?: string;
};

export function useRecordSearch(filters: SearchFilters, enabled: boolean) {
  return useQuery({
    queryKey: ["search", filters],
    enabled,
    queryFn: () =>
      api.get<{ count: number; results: SearchResult[] }>(
        `/api/v1/records/search${query(filters)}`,
      ),
  });
}

export function useLocations(level?: string) {
  return useQuery({
    queryKey: ["locations", level ?? "all"],
    staleTime: 5 * 60_000, // The cadastre's shape does not change mid-session.
    queryFn: () =>
      api.get<{ locations: Location[] }>(`/api/v1/locations${query({ level })}`),
  });
}

export function useVillageParcels(villageId: string | null) {
  return useQuery({
    queryKey: ["gis", "village", villageId],
    enabled: Boolean(villageId),
    queryFn: () =>
      api.get<ParcelFeatureCollection>(`/api/v1/gis/villages/${villageId}/parcels`),
  });
}

// ── Grievances ──────────────────────────────────────────────────────────────

export function useMyGrievances() {
  return useQuery({
    queryKey: ["grievances", "me"],
    queryFn: () =>
      api.get<{
        count: number;
        grievances: Grievance[];
        counts_by_status: Record<string, number>;
      }>("/api/v1/grievances/me"),
  });
}

export function useIssueTypes() {
  return useQuery({
    queryKey: ["grievances", "issue-types"],
    staleTime: Infinity, // A closed vocabulary; it will not change mid-session.
    queryFn: () => api.get<{ issue_types: string[] }>("/api/v1/grievances/issue-types"),
  });
}

// ── Documents ───────────────────────────────────────────────────────────────

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentSummary>(`/api/v1/documents/${documentId}`),
  });
}

/**
 * Poll a document's pipeline progress (§24).
 *
 * Polls only while the job is live, then stops. The API also offers an SSE
 * stream, but a phone that loses signal mid-stream gets no error and no
 * reconnect; a poll that fails simply retries.
 */
export function useProcessingStatus(documentId: string | null) {
  return useQuery({
    queryKey: ["document", documentId, "status"],
    enabled: Boolean(documentId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "SUCCEEDED" || status === "FAILED" ? false : 1500;
    },
    queryFn: () =>
      api.get<ProcessingStatus>(`/api/v1/documents/${documentId}/status`),
  });
}
