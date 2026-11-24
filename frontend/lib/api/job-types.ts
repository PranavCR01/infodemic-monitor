// Raw shapes of the jobs API: backend/app/api/routers/jobs.py on auto/T28 (#81).
// The legacy GET /jobs returns a bare array of the first seven fields; GET /v1/jobs
// returns a page with T28's fields. Both are read by job-adapter.ts.

export type RawJobListItem = {
  job_id: string;
  status: string;
  error_code?: string | null;
  created_at?: string | null;
  filename?: string | null;
  label?: string | null;
  confidence?: number | null;
  // T28
  video_id?: string | null;
  state?: string;
  step?: string | null;
  updated_at?: string | null;
};

export type RawJobListPage = { items: RawJobListItem[]; total: number; limit: number; offset: number };

export type RawJob = {
  job_id: string;
  video_id: string;
  status: string;
  error_code?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  // T28
  state?: string;
  step?: string | null;
  step_label?: string | null;
  attempts?: number;
};

export type RawJobEvent = {
  id: string;
  seq: number;
  kind: "state" | "step" | string;
  state?: string | null;
  status?: string | null;
  step?: string | null;
  step_label?: string | null;
  attempt?: number;
  detail?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type RawJobEvents = {
  job_id: string;
  status: string;
  state: string;
  step?: string | null;
  attempts?: number;
  processing_finished: boolean;
  steps: { key: string; label: string }[];
  pipeline_steps: string[];
  events: RawJobEvent[];
};
