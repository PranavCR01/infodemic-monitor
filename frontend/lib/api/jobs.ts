// Jobs API calls (T28 #81, with fallbacks to today's routes).
import { apiFetch } from "@/lib/api";
import { EMPTY_FILTERS, PAGE_SIZE, type JobFilters } from "@/lib/job-filters";
import type { JobState } from "@/lib/vocabulary";
import { adaptJobList, adaptProgress, type JobRow, type Progress } from "./job-adapter";
import type { RawJob, RawJobEvents } from "./job-types";

/** UI state → the API's status filter values (T28 accepts legacy and §1 names). */
const STATE_FILTER: Record<JobState, string[]> = {
  QUEUED: ["PENDING", "QUEUED"],
  RUNNING: ["RUNNING"],
  RETRYING: ["RETRY_PENDING"],
  NEEDS_REVIEW: ["REVIEW_REQUIRED"],
  COMPLETED: ["COMPLETED", "REJECTED"],
  FAILED: ["FAILED"],
};

const STATES = Object.keys(STATE_FILTER) as JobState[];

/** Filters ↔ URL search params, so a filtered list can be shared and survives reload. */
export function filtersFromSearch(p: URLSearchParams): JobFilters {
  const state = p.get("state") as JobState | null;
  const page = Number(p.get("page"));
  return {
    q: p.get("q") ?? "",
    state: state && STATES.includes(state) ? state : "",
    label: p.get("label") ?? "",
    needsReview: p.get("review") === "1",
    mine: p.get("mine") === "1",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

export function searchFromFilters(f: JobFilters): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.state) p.set("state", f.state);
  if (f.label) p.set("label", f.label);
  if (f.needsReview) p.set("review", "1");
  if (f.mine) p.set("mine", "1");
  if (f.page > 1) p.set("page", String(f.page));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Query string for GET /v1/jobs. "Needs review only" wins over the state filter. */
export function jobsQuery(f: JobFilters = EMPTY_FILTERS): string {
  const p = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((f.page - 1) * PAGE_SIZE) });
  if (f.q) p.set("q", f.q);
  if (f.label) p.set("label", f.label);
  const statuses = f.needsReview ? STATE_FILTER.NEEDS_REVIEW : f.state ? STATE_FILTER[f.state] : [];
  if (statuses.length) p.set("status", statuses.join(","));
  if (f.mine) p.set("mine", "true"); // T33: only the caller's own jobs
  return p.toString();
}

export async function fetchJobs(f: JobFilters, viewerId: string | null = null): Promise<{ rows: JobRow[]; total: number | null } | null> {
  try {
    let res = await apiFetch(`/v1/jobs?${jobsQuery(f)}`);
    if (res.status === 404) res = await apiFetch(`/jobs?limit=50`); // before T28 is deployed
    if (!res.ok) return null;
    return adaptJobList(await res.json(), viewerId);
  } catch {
    return null;
  }
}

/** Progress from T28's events; before T28, a minimal stepper from the job's status. */
export async function fetchProgress(jobId: string): Promise<{ progress: Progress; job: RawJob | null } | null> {
  try {
    const [evRes, jobRes] = await Promise.all([
      apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}/events`),
      apiFetch(`/jobs/${encodeURIComponent(jobId)}`),
    ]);
    const job: RawJob | null = jobRes.ok ? await jobRes.json() : null;
    if (evRes.ok) return { progress: adaptProgress((await evRes.json()) as RawJobEvents), job };
    if (!job) return null;
    const legacyDone = job.status === "SUCCESS" || job.status === "REVIEW_REQUIRED" || job.status === "FAILED";
    return {
      job,
      progress: adaptProgress({
        job_id: job.job_id, status: job.status, state: job.state ?? job.status, step: job.step ?? null,
        attempts: job.attempts ?? 0, processing_finished: legacyDone, steps: [], pipeline_steps: [], events: [],
      }),
    };
  } catch {
    return null;
  }
}

/** Start a new analysis of the same video (a failed job isn't reused by POST /jobs/create). */
export async function retryJob(videoId: string): Promise<string | null> {
  try {
    const res = await apiFetch(`/jobs/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId }),
    });
    if (!res.ok) return null;
    return ((await res.json()) as { job_id: string }).job_id;
  } catch {
    return null;
  }
}
