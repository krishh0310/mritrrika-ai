/**
 * Typed reads of the API, in one place.
 *
 * Every screen calls a hook from here rather than assembling its own URL, so a
 * route change is a one-line edit and two screens can never disagree about
 * what "/api/v1/citizen/my-parcels" returns.
 */

import { useQuery } from "@tanstack/react-query";

import { api, query } from "./api-client";

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

export type ExtractionField = {
  extraction_id: string;
  field: string;
  raw_value: string | null;
  normalized_value: string | null;
  corrected_value: string | null;
  effective_value: string | null;
  ocr_confidence: number | null;
  extraction_confidence: number | null;
  final_confidence: number | null;
  confidence_breakdown: Record<string, number> | null;
  bbox: [number, number, number, number];
  status: string;
  /** Which page the bbox is on. A PDF upload has one image per page. */
  page_number: number;
  row_index: number | null;
  model_version: string | null;
};

export type OcrBlock = {
  text: string;
  confidence: number;
  bbox: [number, number, number, number];
  reading_order: number;
  page_number: number;
};

export type DocumentPageInfo = {
  page_number: number;
  width: number | null;
  height: number | null;
};

export type ValidationFinding = {
  rule: string;
  severity: string;
  message: string;
  field: string | null;
};

export type Workspace = {
  document_id: string;
  state: string;
  document_type: string;
  quality: Quality | null;
  page: { width: number | null; height: number | null };
  pages: DocumentPageInfo[];
  fields: ExtractionField[];
  ocr_blocks: OcrBlock[];
  findings: ValidationFinding[];
  is_synthetic: boolean;
};

export type AnomalyFlag = {
  anomaly_type: string;
  score: number | null;
  explanation: string;
  evidence: Record<string, unknown> | null;
  status: string;
  model_version: string | null;
};

export type ApprovalWorkspace = Workspace & {
  corrections: {
    field: string;
    model_prediction: string | null;
    corrected_value: string | null;
    confidence_at_correction: number | null;
    model_version: string | null;
    reason: string | null;
    corrected_by: string | null;
    at: string | null;
  }[];
  anomalies: AnomalyFlag[];
  decisions: { decision: string; reason: string | null; at: string | null }[];
  parcel: {
    parcel_id: string;
    khasra_number: string;
    khata_number: string | null;
    area_value: number;
    area_unit: string;
    land_class: string | null;
    village: string | null;
  } | null;
  ownership_history: OwnershipSpan[];
  mutations: {
    mutation_id: string;
    mutation_number: string;
    mutation_type: string;
    effective_date: string;
    registration_date: string | null;
    status: string;
    notes: string | null;
  }[];
  audit_timeline: {
    sequence: number;
    action: string;
    actor_role: string | null;
    reason: string | null;
    at: string | null;
  }[];
  original_url: string | null;
  unlinked_reason?: string;
};

export type DocumentSummary = {
  document_id: string;
  document_type: string;
  state: string;
  quality_score: number | null;
  quality_recommendation: string | null;
  quality_report: Record<string, unknown> | null;
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

export type QueueTask = {
  task_id: string;
  document_id: string;
  document_type: string;
  state: string;
  status: string;
  priority: number;
  lowest_confidence: number | null;
  anomaly_count: number;
  quality_score: number | null;
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

export type AiAnswer = {
  answer: string;
  /** What the answer was built from. §18 forbids an uncited claim. */
  citations: { type: string; id: string; detail: string | null }[];
  records: Record<string, unknown>[];
  intent: string;
  /** False when no LLM was reachable and the structured result stands alone (§82). */
  llm_used: boolean;
  degraded: boolean;
  /** Officers are scoped by jurisdiction, citizens by ownership (§18, §35). */
  audience: "citizen" | "officer";
  is_synthetic: boolean;
};

// ── Citizen ─────────────────────────────────────────────────────────────────

export const citizenKeys = {
  dashboard: ["citizen", "dashboard"] as const,
  parcels: ["citizen", "parcels"] as const,
  parcel: (id: string) => ["citizen", "parcel", id] as const,
  history: (id: string) => ["citizen", "history", id] as const,
};

export function useCitizenDashboard() {
  return useQuery({
    queryKey: citizenKeys.dashboard,
    queryFn: () => api.get<CitizenDashboard>("/api/v1/citizen/dashboard"),
  });
}

export function useMyParcels() {
  return useQuery({
    queryKey: citizenKeys.parcels,
    queryFn: () =>
      api.get<{ count: number; parcels: Holding[] }>("/api/v1/citizen/my-parcels"),
  });
}

export function useOwnershipHistory(parcelId: string | null) {
  return useQuery({
    queryKey: citizenKeys.history(parcelId ?? ""),
    enabled: Boolean(parcelId),
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

export function useLocations(level?: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["locations", level ?? "all"],
    enabled: options.enabled ?? true,
    staleTime: 5 * 60_000, // The cadastre's shape does not change mid-session.
    queryFn: () =>
      api.get<{ locations: Location[] }>(`/api/v1/locations${query({ level })}`),
  });
}

export type ParcelFeatureCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: string; coordinates: unknown };
    properties: Record<string, unknown>;
  }[];
};

export function useVillageParcels(villageId: string | null) {
  return useQuery({
    queryKey: ["gis", "village", villageId],
    enabled: Boolean(villageId),
    queryFn: () =>
      api.get<ParcelFeatureCollection>(`/api/v1/gis/villages/${villageId}/parcels`),
  });
}

// ── Documents and processing ────────────────────────────────────────────────

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentSummary>(`/api/v1/documents/${documentId}`),
  });
}

/**
 * Poll a document's pipeline progress (§24).
 *
 * Polls only while the job is live, then stops. The SSE stream exists too, but
 * polling is what survives a proxy that buffers event streams, and the payload
 * is four fields.
 */
export function useProcessingStatus(documentId: string, active: boolean) {
  return useQuery({
    queryKey: ["document", documentId, "status"],
    enabled: active,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "SUCCEEDED" || status === "FAILED" ? false : 1200;
    },
    queryFn: () =>
      api.get<ProcessingStatus>(`/api/v1/documents/${documentId}/status`),
  });
}

// ── Officer queues and workspaces ───────────────────────────────────────────

export function useVerificationQueue() {
  return useQuery({
    queryKey: ["verifications"],
    queryFn: () =>
      api.get<{ count: number; tasks: QueueTask[] }>("/api/v1/verifications"),
  });
}

export function useVerificationWorkspace(documentId: string) {
  return useQuery({
    queryKey: ["verifications", documentId, "workspace"],
    queryFn: () =>
      api.get<Workspace>(`/api/v1/verifications/${documentId}/workspace`),
  });
}

export function useApprovalQueue() {
  return useQuery({
    queryKey: ["approvals"],
    queryFn: () =>
      api.get<{ count: number; documents: QueueTask[] }>("/api/v1/approvals"),
  });
}

export function useApprovalWorkspace(documentId: string) {
  return useQuery({
    queryKey: ["approvals", documentId, "workspace"],
    queryFn: () =>
      api.get<ApprovalWorkspace>(`/api/v1/approvals/${documentId}/workspace`),
  });
}

// ── Dashboards ──────────────────────────────────────────────────────────────

export type Cards = Record<string, number | null>;

export type Quality = {
  blur_score: number;
  contrast_score: number;
  resolution_quality: string;
  resolution_score: number;
  skew_angle: number;
  skew_score: number;
  brightness_score: number;
  overall_score: number;
  recommended_action: string;
};

export function useDeoDashboard() {
  return useQuery({
    queryKey: ["dashboard", "deo"],
    queryFn: () =>
      api.get<{ cards: Cards; recent_documents: DocumentSummary[] }>(
        "/api/v1/dashboard/deo",
      ),
  });
}

export function useVerifierDashboard() {
  return useQuery({
    queryKey: ["dashboard", "verifier"],
    queryFn: () => api.get<{ cards: Cards }>("/api/v1/dashboard/verifier"),
  });
}

export function useTehsildarDashboard() {
  return useQuery({
    queryKey: ["dashboard", "tehsildar"],
    queryFn: () =>
      api.get<{ cards: Cards; totals: Record<string, number> }>(
        "/api/v1/dashboard/tehsildar",
      ),
  });
}

export type Analytics = {
  documents_by_state: Record<string, number>;
  documents_by_type: Record<string, number>;
  documents_by_quality: Record<string, number>;
  anomalies_by_type: Record<string, number>;
  confidence_bands: { HIGH: number; MEDIUM: number; LOW: number };
  workload: { role: string; user_id: string; documents: number }[];
};

export function useAnalytics() {
  return useQuery({
    queryKey: ["dashboard", "analytics"],
    queryFn: () => api.get<Analytics>("/api/v1/dashboard/analytics"),
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

export function useGrievanceQueue(status?: string) {
  return useQuery({
    queryKey: ["grievances", "queue", status ?? "all"],
    queryFn: () =>
      api.get<{
        count: number;
        grievances: Grievance[];
        counts_by_status: Record<string, number>;
      }>(`/api/v1/grievances${query({ status })}`),
  });
}

export function useIssueTypes() {
  return useQuery({
    queryKey: ["grievances", "issue-types"],
    staleTime: Infinity, // A closed vocabulary; it will not change mid-session.
    queryFn: () => api.get<{ issue_types: string[] }>("/api/v1/grievances/issue-types"),
  });
}

// ── Anomalies and audit ─────────────────────────────────────────────────────

export function useAnomalies(status = "OPEN") {
  return useQuery({
    queryKey: ["anomalies", status],
    queryFn: () =>
      api.get<{
        count: number;
        flags: (AnomalyFlag & { flag_id: string; parcel_id: string | null; khasra_number: string | null })[];
      }>(`/api/v1/anomalies${query({ status })}`),
  });
}

export type AuditEvent = {
  sequence: number;
  timestamp: string;
  action: string;
  actor_role: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  reason: string | null;
  event_hash: string;
  previous_hash: string;
};

export function useAuditTrail(documentId: string) {
  return useQuery({
    queryKey: ["audit", documentId],
    queryFn: () =>
      api.get<{ document_id: string; events: AuditEvent[] }>(
        `/api/v1/audit/documents/${documentId}`,
      ),
  });
}

export function useAuditChain(enabled: boolean) {
  return useQuery({
    queryKey: ["audit", "verify"],
    enabled,
    queryFn: () =>
      api.get<{
        valid: boolean;
        events: number;
        problems: string[];
        mechanism: string;
      }>("/api/v1/audit/verify"),
  });
}
