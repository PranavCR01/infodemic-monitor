// MOCK DATA for the jobs list and the progress stepper, in T28's (#81) shapes.
import type { RawJobEvents, RawJobListPage } from "../job-types";

const STEPS = [
  ["uploaded", "Uploaded"], ["transcribing", "Transcribing"], ["reading_on_screen_text", "Reading on-screen text"],
  ["finding_claims", "Finding claims"], ["checking_stance", "Checking stance"], ["searching_evidence", "Searching evidence"],
  ["verifying", "Verifying"], ["final_checks", "Final checks"],
].map(([key, label]) => ({ key, label }));
const ALL = STEPS.map((s) => s.key);

const ev = (seq: number, kind: "state" | "step", v: string, at: string, attempt = 1) =>
  kind === "step" ? { id: `e${seq}`, seq, kind, step: v, attempt, created_at: at } : { id: `e${seq}`, seq, kind, state: v, attempt, created_at: at };

const base = [
  ev(1, "state", "QUEUED", "2026-11-23T10:00:00Z"),
  ev(2, "state", "RUNNING", "2026-11-23T10:00:05Z"),
  ev(3, "step", "uploaded", "2026-11-23T10:00:05Z"),
  ev(4, "step", "transcribing", "2026-11-23T10:00:06Z"),
  ev(5, "step", "reading_on_screen_text", "2026-11-23T10:00:18Z"),
  ev(6, "step", "finding_claims", "2026-11-23T10:00:27Z"),
  ev(7, "step", "checking_stance", "2026-11-23T10:00:35Z"),
  ev(8, "step", "searching_evidence", "2026-11-23T10:00:41Z"),
];

export const MOCK_RUNNING: RawJobEvents = {
  job_id: "job-run", status: "STARTED", state: "RUNNING", step: "searching_evidence", attempts: 1,
  processing_finished: false, steps: STEPS, pipeline_steps: ALL, events: base,
};

export const MOCK_RETRYING: RawJobEvents = {
  ...MOCK_RUNNING, job_id: "job-retry", state: "RETRY_PENDING", attempts: 2,
  events: [...base, ev(9, "state", "RETRY_PENDING", "2026-11-23T10:01:10Z", 2)],
};

export const MOCK_FAILED: RawJobEvents = {
  ...MOCK_RUNNING, job_id: "job-fail", status: "FAILED", state: "FAILED", step: "transcribing", processing_finished: true,
  events: [...base.slice(0, 4), ev(9, "state", "FAILED", "2026-11-23T10:00:30Z")],
};

export const MOCK_QUEUED: RawJobEvents = {
  job_id: "job-queued", status: "PENDING", state: "QUEUED", step: null, attempts: 0, processing_finished: false,
  steps: STEPS, pipeline_steps: ALL, events: [ev(1, "state", "QUEUED", "2026-11-23T10:00:00Z")],
};

export const MOCK_DONE: RawJobEvents = {
  ...MOCK_RUNNING, job_id: "job-done", status: "SUCCESS", state: "COMPLETED", step: "final_checks", processing_finished: true,
  events: [...base, ev(9, "step", "verifying", "2026-11-23T10:01:12Z"), ev(10, "step", "final_checks", "2026-11-23T10:01:30Z"), ev(11, "state", "COMPLETED", "2026-11-23T10:01:33Z")],
};

export const MOCK_SINGLE_CALL: RawJobEvents = {
  ...MOCK_RUNNING, job_id: "job-single", step: "transcribing",
  pipeline_steps: ["uploaded", "transcribing", "verifying", "searching_evidence"],
  events: base.slice(0, 4),
};

export const MOCK_JOB_PAGE: RawJobListPage = {
  total: 5, limit: 20, offset: 0,
  items: [
    { job_id: "j1", status: "STARTED", state: "RUNNING", step: "searching_evidence", filename: "hot-water-flu.mp4", created_at: "2026-11-23T10:00:00Z" },
    { job_id: "j2", status: "STARTED", state: "RETRY_PENDING", step: "verifying", filename: "garlic-bp.mov", created_at: "2026-11-23T09:50:00Z" },
    { job_id: "j3", status: "REVIEW_REQUIRED", state: "REVIEW_REQUIRED", filename: "sea-moss-thyroid.mp4", label: "MISINFO", created_at: "2026-11-23T09:00:00Z" },
    { job_id: "j4", status: "SUCCESS", state: "COMPLETED", filename: "pharmacist-explains-garlic.mov", label: "DEBUNKING", created_at: "2026-11-22T15:00:00Z" },
    { job_id: "j5", status: "FAILED", state: "FAILED", error_code: "TRANSCRIPTION_ERROR", filename: "silent-clip.mp4", created_at: "2026-11-22T12:00:00Z" },
  ],
};
