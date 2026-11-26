// Raw shapes of the review API: backend/app/api/routers/reviews.py (T27, T33, T34).

export type RawReasonCode = "SYSTEM_CORRECT" | "CLAIM_OVERGENERALISED" | "EVIDENCE_MISREAD" | "STANCE_MISREAD" | "MISSING_SOURCE" | "OTHER";

export type RawDecision = {
  reviewer_id: string;
  reviewer_name?: string | null; // T34: display name, else email
  reviewer_email?: string | null;
  action: string; // APPROVE | CORRECT | MARK_INSUFFICIENT | REJECT | REQUEST_REANALYSIS
  reason?: string | null;
  reason_code?: RawReasonCode | null; // T34; null on decisions made before it
  corrected_label?: string | null;
  corrections?: Record<string, unknown> | null;
  decided_at?: string | null;
};

export type RawQueueItem = {
  review_id: string;
  job_id: string;
  video_id?: string | null;
  filename?: string | null;
  job_status?: string | null;
  submitted_by?: string | null; // T33: the submitter's Supabase user id
  submitted_by_name?: string | null; // T34
  submitted_by_email?: string | null;
  is_own?: boolean; // T34: the caller submitted the job or owns the video
  // T34: an open HIGH case needs each reviewer's own judgement first. While
  // `system_view_withheld`, the proposed label, reasons and rules fired are empty.
  blind_step_required?: boolean;
  system_view_withheld?: boolean;
  status: "OPEN" | "RESOLVED" | "SUPERSEDED"; // T55: SUPERSEDED = closed by a re-analysis, never decided
  superseded_by_job_id?: string | null; // T55
  severity?: string | null;
  reasons: string[];
  rules_fired?: Record<string, unknown>[];
  proposed_label?: string | null;
  created_at: string;
  age_seconds: number;
  decision?: RawDecision | null;
};

export type RawQueuePage = { items: RawQueueItem[]; total: number; limit: number; offset: number };

export type RawAudit = {
  id: string;
  actor_id: string;
  actor_name?: string | null; // T34
  actor_email?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  reason?: string | null;
  details?: Record<string, unknown>;
  created_at: string;
};

/** T34: one claim of the case. `stance` / `verdict` are the system's, null while withheld. */
export type RawCaseClaim = {
  claim_id: string;
  text?: string | null;
  category?: string | null;
  start?: number | null;
  end?: number | null;
  severity?: string | null;
  stance?: string | null;
  verdict?: string | null;
};

/** T34: the caller's own blind judgement, once given. */
export type RawPreReveal = {
  id: string;
  reviewer_id: string;
  claims: Record<string, { stance?: string; verdict?: string }>;
  note?: string | null;
  case_severity?: string | null;
  created_at: string;
};

export type RawCase = RawQueueItem & {
  claims?: RawCaseClaim[];
  pre_reveal?: RawPreReveal | null;
  claim_severities?: Record<string, unknown> | null;
  pipeline_version?: string | null;
  audit_trail?: RawAudit[];
};

export type RawMe = { user_id: string; email?: string | null; display_name?: string | null; role: string; permissions: string[] };
