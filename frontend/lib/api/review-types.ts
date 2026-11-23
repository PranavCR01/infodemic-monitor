// Raw shapes of the review API: backend/app/api/routers/reviews.py on auto/T27 (#78).
// Fields marked PROPOSED were asked of T27 and don't exist yet.

export type RawDecision = {
  reviewer_id: string;
  action: string; // APPROVE | CORRECT | MARK_INSUFFICIENT | REJECT | REQUEST_REANALYSIS
  reason?: string | null;
  corrected_label?: string | null;
  corrections?: Record<string, unknown> | null;
  decided_at?: string | null;
  reviewer_name?: string | null; // PROPOSED
};

export type RawQueueItem = {
  review_id: string;
  job_id: string;
  video_id?: string | null;
  filename?: string | null;
  job_status?: string | null;
  status: "OPEN" | "RESOLVED";
  severity?: string | null;
  reasons: string[];
  rules_fired?: Record<string, unknown>[];
  proposed_label?: string | null;
  created_at: string;
  age_seconds: number;
  decision?: RawDecision | null;
  submitted_by?: string | null; // PROPOSED
  is_own?: boolean; // PROPOSED
};

export type RawQueuePage = { items: RawQueueItem[]; total: number; limit: number; offset: number };

export type RawAudit = {
  id: string;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason?: string | null;
  details?: Record<string, unknown>;
  created_at: string;
  actor_name?: string | null; // PROPOSED
};

export type RawCase = RawQueueItem & {
  claim_severities?: Record<string, unknown> | null;
  audit_trail?: RawAudit[];
};

export type RawMe = { user_id: string; email?: string | null; role: string; permissions: string[] };
