// ADAPTER: jobs list and job progress (T28) → what the jobs page and the stepper render.
import { isVideoLabel, toJobState, type JobState, type VideoLabel } from "@/lib/vocabulary";
import type { RawJobEvents, RawJobListItem, RawJobListPage } from "./job-types";

/** Step names (HANDOFF §6.4). The design's wording, not the API's labels. */
export const STEP_TEXT: Record<string, string> = {
  uploaded: "Uploaded",
  transcribing: "Transcribing speech",
  reading_on_screen_text: "Reading on-screen text",
  finding_claims: "Finding claims",
  checking_stance: "Checking stance",
  searching_evidence: "Searching evidence",
  verifying: "Verifying",
  final_checks: "Final checks",
};

export const stepText = (key: string | null | undefined, fallback?: string | null) =>
  (key && STEP_TEXT[key]) || fallback || "Working";

export type JobRow = {
  jobId: string;
  filename: string;
  state: JobState | null;
  rawStatus: string;
  step: string | null;
  label: VideoLabel | null;
  submittedAt: string | null;
  active: boolean;
};

const ACTIVE: (JobState | null)[] = ["QUEUED", "RUNNING", "RETRYING"];

export function adaptJobRow(r: RawJobListItem): JobRow {
  // T28's §1 state is finer (RETRY_PENDING); fall back to the legacy status.
  const state = toJobState(r.state ?? r.status);
  return {
    jobId: r.job_id,
    filename: r.filename ?? "Untitled video",
    state,
    rawStatus: r.state ?? r.status,
    step: state === "RUNNING" || state === "RETRYING" ? stepText(r.step, null) : null,
    label: isVideoLabel(r.label) ? r.label : null,
    submittedAt: r.created_at ?? null,
    active: ACTIVE.includes(state),
  };
}

/** Accepts the legacy array and T28's page. */
export function adaptJobList(raw: RawJobListItem[] | RawJobListPage): { rows: JobRow[]; total: number | null } {
  if (Array.isArray(raw)) return { rows: raw.map(adaptJobRow), total: null };
  return { rows: raw.items.map(adaptJobRow), total: raw.total };
}

// ---------------------------------------------------------------- stepper

export type StepStatus = "done" | "now" | "warn" | "fail" | "pending";
export type Step = { key: string; text: string; status: StepStatus; seconds: number | null };

export type Progress = {
  state: JobState | null;
  steps: Step[];
  currentText: string | null;
  attempt: number;
  finished: boolean;
  startedAt: string | null;
  failedStep: string | null;
};

const ts = (s: string | null | undefined) => (s ? Date.parse(s) : NaN);

/**
 * Stepper from GET /v1/jobs/{id}/events. Only the steps this job's pipeline goes
 * through are shown. Durations come from when each step started and the next began.
 */
export function adaptProgress(raw: RawJobEvents): Progress {
  const state = toJobState(raw.state ?? raw.status);
  // The order this job's pipeline runs in (the single call verifies before it searches),
  // limited to steps the API names.
  const known = new Set(raw.steps.map((s) => s.key));
  const keys = raw.pipeline_steps.filter((k) => known.has(k));
  const stepEvents = raw.events.filter((e) => e.kind === "step" && e.step).sort((a, b) => a.seq - b.seq);
  const reached = new Set(stepEvents.map((e) => e.step!));
  const current = raw.step ?? stepEvents[stepEvents.length - 1]?.step ?? null;
  const currentIdx = current ? keys.indexOf(current) : -1;
  const finishedOk = raw.processing_finished && state !== "FAILED";
  const allEvents = [...raw.events].sort((a, b) => a.seq - b.seq);

  const seconds = (key: string): number | null => {
    const startIdx = allEvents.findIndex((e) => e.kind === "step" && e.step === key);
    if (startIdx < 0) return null;
    const start = ts(allEvents[startIdx].created_at);
    const next = allEvents.slice(startIdx + 1).find((e) => e.kind === "step" || e.state === "COMPLETED" || e.state === "REVIEW_REQUIRED");
    const end = ts(next?.created_at);
    return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, Math.round((end - start) / 1000)) : null;
  };

  const steps: Step[] = keys.map((key, i) => {
    let status: StepStatus = "pending";
    if (finishedOk) status = "done";
    else if (i < currentIdx || (currentIdx < 0 && reached.has(key))) status = "done";
    else if (i === currentIdx) status = state === "FAILED" ? "fail" : state === "RETRYING" ? "warn" : state === "QUEUED" ? "pending" : "now";
    return { key, text: stepText(key, raw.steps.find((s) => s.key === key)?.label), status, seconds: status === "done" ? seconds(key) : null };
  });

  const first = allEvents[0]?.created_at ?? null;
  return {
    state,
    steps,
    currentText: current && !finishedOk ? stepText(current) : null,
    attempt: raw.attempts ?? 0,
    finished: raw.processing_finished,
    startedAt: first,
    failedStep: state === "FAILED" && current ? stepText(current) : null,
  };
}

/** "1:12" elapsed, for the stepper's timer and list sub-lines. */
export function elapsed(fromIso: string | null, now = Date.now()): string {
  const from = ts(fromIso);
  if (!Number.isFinite(from)) return "";
  const s = Math.max(0, Math.floor((now - from) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Plain-language failure reasons by error code (the job page; T28 events add the step). */
export const FAILURE_TEXT: Record<string, string> = {
  STORAGE_ERROR: "We couldn't read the video file.",
  TRANSCRIPTION_ERROR: "We couldn't transcribe the speech in the video.",
  INFERENCE_ERROR: "The analysis stopped before it finished.",
  GROUNDING_ERROR: "The evidence search stopped before it finished.",
  DISPATCH_FAILED: "The analysis couldn't be started.",
};
export const failureText = (code: string | null | undefined) =>
  (code && FAILURE_TEXT[code]) || "The analysis stopped because of an unexpected problem.";
