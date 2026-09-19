/**
 * GENERATED FILE -- DO NOT EDIT.
 *
 * Emitted from packages/domain (the Python source of truth) by
 * scripts/generate_shared_types.py. Edit the Pydantic models / StrEnums there
 * and regenerate; hand edits here will be overwritten and will fail CI.
 */


// ─── Controlled vocabularies (packages/domain/enums.py) ───

export type AnomalyType =
  | 'AREA_JUMP'
  | 'INVALID_CHRONOLOGY'
  | 'DUPLICATE_PARCEL'
  | 'MISSING_MUTATION'
  | 'LOCATION_MISMATCH'
  | 'REPEATED_MODIFICATION'
  | 'UNUSUAL_OWNERSHIP_CHANGE'
  | 'DUPLICATE_DOCUMENT';

export type AreaUnit =
  | 'BIGHA'
  | 'BISWA'
  | 'ACRE'
  | 'HECTARE'
  | 'SQUARE_METRE'
  | 'GUNTHA'
  | 'CENT';

export type ConfidenceBand =
  | 'HIGH'
  | 'MEDIUM'
  | 'LOW';

export type DocumentState =
  | 'UPLOADED'
  | 'QUALITY_CHECK'
  | 'PROCESSING'
  | 'AI_EXTRACTED'
  | 'NEEDS_VERIFICATION'
  | 'UNDER_VERIFICATION'
  | 'VERIFIED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'RESCAN_REQUIRED'
  | 'ARCHIVED';

export type DocumentType =
  | 'KHASRA'
  | 'KHATAUNI'
  | 'JAMABANDI'
  | 'RECORD_OF_RIGHTS'
  | 'MUTATION_REGISTER'
  | 'SUPPORTING';

export type FieldName =
  | 'OWNER'
  | 'GUARDIAN'
  | 'KHASRA'
  | 'KHATA'
  | 'VILLAGE'
  | 'TEHSIL'
  | 'DISTRICT'
  | 'STATE'
  | 'AREA'
  | 'AREA_UNIT'
  | 'LAND_CLASS'
  | 'MUTATION'
  | 'DATE'
  | 'RECORD_YEAR'
  | 'SHARE'
  | 'REMARK';

export type FieldStatus =
  | 'AUTO_ACCEPTED'
  | 'NEEDS_REVIEW'
  | 'VERIFIER_APPROVED'
  | 'VERIFIER_CORRECTED'
  | 'ILLEGIBLE'
  | 'ESCALATED';

export type GrievanceStatus =
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'ACTION_REQUIRED'
  | 'RESOLVED'
  | 'REJECTED';

export type MutationType =
  | 'SALE'
  | 'INHERITANCE'
  | 'GIFT'
  | 'PARTITION'
  | 'COURT_DECREE'
  | 'CORRECTION';

export type ProcessingStage =
  | 'upload'
  | 'quality'
  | 'preprocessing'
  | 'ocr'
  | 'layout'
  | 'extraction'
  | 'normalization'
  | 'validation'
  | 'confidence'
  | 'complete';

export type QualityRecommendation =
  | 'PROCESS'
  | 'PROCESS_WITH_WARNING'
  | 'RESCAN_RECOMMENDED'
  | 'REJECT_QUALITY';

export type Role =
  | 'CITIZEN'
  | 'DEO'
  | 'VERIFIER'
  | 'TEHSILDAR';

export type ValidationSeverity =
  | 'info'
  | 'warning'
  | 'error';


// ─── Record schema (packages/domain/records.py) ───

export interface Area {
  value: number;
  unit: AreaUnit;
  unit_raw?: string;
}

export interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface ExtractedField {
  field: FieldName;
  raw_value?: string;
  normalized_value?: string;
  ocr_confidence?: number;
  extraction_confidence?: number;
  final_confidence: number;
  bbox?: BoundingBox;
  source_page?: number;
  status?: FieldStatus;
  model_version?: string;
  validation_message?: string;
}

export interface OwnerShare {
  owner_id?: string;
  name: string;
  share?: string;
  guardian_name?: string;
}

export interface CanonicalLandRecord {
  document_id: string;
  parcel_id?: string;
  document_type: DocumentType;
  state: string;
  district: string;
  tehsil: string;
  village: string;
  khasra_number?: string;
  khata_number?: string;
  owners?: OwnerShare[];
  area?: Area;
  land_class?: string;
  record_year?: string;
  fields?: ExtractedField[];
  extracted_at?: string;
  pipeline_version?: string;
  is_synthetic?: boolean;
}


// ─── Confidence banding (packages/domain/confidence.py) ───

export const HIGH_CONFIDENCE_THRESHOLD = 0.85;
export const MEDIUM_CONFIDENCE_THRESHOLD = 0.6;


// ─── Document state machine (packages/domain/state_machine.py) ───

export const ALLOWED_TRANSITIONS: Record<DocumentState, DocumentState[]> = {
  UPLOADED: ['QUALITY_CHECK', 'REJECTED'],
  QUALITY_CHECK: ['PROCESSING', 'REJECTED', 'RESCAN_REQUIRED'],
  PROCESSING: ['AI_EXTRACTED', 'REJECTED', 'RESCAN_REQUIRED'],
  AI_EXTRACTED: ['NEEDS_VERIFICATION'],
  NEEDS_VERIFICATION: ['PROCESSING', 'UNDER_VERIFICATION'],
  UNDER_VERIFICATION: ['NEEDS_VERIFICATION', 'RESCAN_REQUIRED', 'VERIFIED'],
  VERIFIED: ['PENDING_APPROVAL'],
  PENDING_APPROVAL: ['APPROVED', 'REJECTED', 'RESCAN_REQUIRED', 'UNDER_VERIFICATION'],
  APPROVED: ['ARCHIVED'],
  REJECTED: ['ARCHIVED'],
  RESCAN_REQUIRED: ['ARCHIVED', 'UPLOADED'],
  ARCHIVED: []
};
