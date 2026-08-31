/**
 * Shared interface vocabulary (§77 `packages/ui`).
 *
 * Components live here rather than in apps/web so the officer screens, the
 * citizen portal and any future surface all render a confidence band or a
 * document status the same way. A status that means one thing on one screen
 * and another elsewhere is worse than no status component at all.
 */

export { cn } from "./cn";

export {
  ConfidenceBadge,
  ConfidenceBar,
  bandFor,
  HIGH_THRESHOLD,
  MEDIUM_THRESHOLD,
  type ConfidenceBand,
} from "./confidence-badge";

export { ProvenanceStrip, ProvenanceCaption } from "./provenance";

export {
  DocumentStatus,
  GrievanceStatus,
  QualityVerdict,
  RoleBadge,
  SyntheticNotice,
  DOCUMENT_STATES,
  GRIEVANCE_STATES,
  QUALITY_VERDICTS,
} from "./status";

export {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  ForbiddenState,
  Input,
  LoadingState,
  Select,
  StatCard,
  Table,
  Td,
  Textarea,
  Th,
  type ButtonProps,
} from "./primitives";

export { ParcelCard } from "./parcel-card";
