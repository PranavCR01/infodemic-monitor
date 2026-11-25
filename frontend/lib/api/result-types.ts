// Raw shapes of GET /jobs/{job_id}/result, as the backend sends them.
// - Fields without a comment exist today (T11).
// - T26 fields: backend/app/api/result_models.py on auto/T26 (not merged yet).
// - T30 (misinfo_basis, label_display) and T31 (claims[].search_trail): merged
//   into langgraph-build (#86, #84).
// Everything after T11 is optional here, so the page works against today's API.

export type RawSegment = {
  segment_id: string;
  source: "speech" | "screen";
  start_seconds: number;
  end_seconds: number;
  text: string;
  confidence?: number | null;
};

export type RawEvidence = {
  evidence_id: string;
  title: string;
  pmid?: string | null;
  url?: string | null;
  study_type?: string | null;
  relation: string; // SUPPORTS | CONTRADICTS | CONSIDERED
  // T26
  source_kind?: "pubmed" | "reference" | "library" | "other";
  doi?: string | null;
  year?: number | null;
  publisher?: string | null;
  publication_type?: string[];
  abstract_snippet?: string;
  rank?: number | null;
};

export type RawClaimSeverity = {
  claim_id: string;
  severity?: string | null;
  table_severity?: string | null;
  basis?: string[];
  override?: Record<string, unknown> | null;
};

export type RawClaim = {
  claim_id: string;
  text: string;
  category: string;
  start_seconds: number;
  end_seconds: number;
  label?: string | null;
  deciding: boolean;
  stance?: string | null;
  verdict?: string | null;
  verdict_explanation?: string;
  limitations?: string[];
  evidence?: RawEvidence[];
  // T26
  id?: string;
  claim_kind?: string | null;
  source_segment_ids?: string[];
  modality?: "speech" | "screen" | "both" | null;
  stance_rationale?: string;
  stance_segment_ids?: string[];
  stance_quotes?: RawSegment[];
  critic?: { decision: string; issues?: string[]; requires_review?: boolean } | null;
  severity?: RawClaimSeverity | null;
  // T31
  search_trail?: RawSearchTrail | null;
};

export type RawReason = {
  code: string;
  rule: string;
  claim_id?: string | null;
  detail?: string | null;
  text: string;
  raw: string;
};

export type RawReview = {
  status: string; // REVIEW_REQUIRED | VERIFIED | CORRECTED | REJECTED | REANALYSIS_REQUESTED
  reasons: string[];
  // T26
  review_id?: string;
  case_status?: "OPEN" | "RESOLVED";
  resolved?: boolean;
  action?: string | null;
  reason_details?: RawReason[];
  severity?: string | null;
  proposed_label?: string | null;
  corrected_label?: string | null;
  decision_reason?: string | null;
  created_at?: string | null;
  decided_at?: string | null;
};

/** T31 (#84): backend/app/core/schemas/search_trail.py SearchTrailView (subset we read). */
export type RawSearchTrail = {
  version?: number;
  recorded?: "graph" | "queries_only";
  pubmed_queries?: { round: number; query: string; results?: number | null; failed?: boolean; repeat?: boolean }[];
  references?: { source_id: string; name: string; publisher?: string; sites?: string[]; passages?: number }[];
  library?: { fired: boolean; passages?: number } | null;
  counts: { retrieved?: number | null; screened: number; kept: number };
  budget: { rounds_used: number; rounds_max: number; exhausted: boolean; evidence_cap?: number };
};

export type RawResult = {
  job_id: string;
  filename?: string | null;
  label: string;
  confidence: number;
  explanation: string;
  submitted_at?: string | null;
  created_at?: string | null;
  pipeline?: string | null;
  fallback_reason?: string | null;
  review?: RawReview | null;
  claims?: RawClaim[];
  // T26
  video_id?: string | null;
  status?: string | null;
  // T36: graph_v1+<short git sha>+p<routing hash> on new results; plain "graph_v1" on older ones.
  pipeline_version?: string | null;
  // T36: the prompt version and model per step that the hash covers. Kept for tracing
  // only and NEVER displayed or exported: the interface never names models (brief).
  routing_snapshot?: Record<string, unknown> | null;
  decision_rule?: string | null;
  deciding_claim_ids?: string[];
  transcript_segments?: RawSegment[];
  ocr_segments?: RawSegment[];
  // T30
  misinfo_basis?: string | null;
  /** The backend's display text; the UI uses lib/vocabulary.ts instead, for one source of wording. */
  label_display?: string | null;
};
