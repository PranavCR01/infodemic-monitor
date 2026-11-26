// T55: POST /v1/videos/{video_id}/reanalyse, a deliberate new analysis of a video.
// Owner or admin only (the server checks again); limited per video and per user per 24 h.
import { apiFetch } from "@/lib/api";

export const REANALYSE_REASON_MAX = 2000;

export type ReanalyseOutcome =
  | { ok: true; jobId: string; remaining: number | null }
  | { ok: false; message: string };

/** "in about 3 hours", "in about 20 minutes", "in a minute". Rounded up: never sooner than true. */
export function retryText(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 60) return "in a minute";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `in about ${minutes} minutes`;
  const hours = Math.ceil(minutes / 60);
  return hours === 1 ? "in about an hour" : `in about ${hours} hours`;
}

type RateLimitDetail = {
  code?: string;
  limit_kind?: "per_video" | "per_user";
  retry_after_seconds?: number;
  limit?: number;
  window_hours?: number;
};

/** The plain message for a 429 (T55 limits). Retry-After wins over the body when both are sent. */
export function rateLimitMessage(detail: RateLimitDetail | null, retryAfterHeader: string | null): string {
  const header = retryAfterHeader !== null ? Number(retryAfterHeader) : NaN;
  const seconds = Number.isFinite(header) ? header : detail?.retry_after_seconds ?? NaN;
  const when = retryText(seconds);
  const hours = detail?.window_hours ?? 24;
  const limit = detail?.limit;
  if (detail?.limit_kind === "per_user") {
    return `You've used all ${limit ? `${limit} ` : ""}re-analyses allowed in ${hours} hours. You can start another one ${when}.`;
  }
  return `This video has already been re-analysed ${limit ? `${limit} times ` : "as often as allowed "}in the last ${hours} hours. You can re-analyse it again ${when}.`;
}

async function detailOf(res: Response): Promise<unknown> {
  try {
    return ((await res.json()) as { detail?: unknown }).detail ?? null;
  } catch {
    return null;
  }
}

export async function requestReanalysis(videoId: string, reason: string): Promise<ReanalyseOutcome> {
  const note = reason.trim();
  if (note.length > REANALYSE_REASON_MAX) return { ok: false, message: `Keep the reason under ${REANALYSE_REASON_MAX} characters.` };
  try {
    const res = await apiFetch(`/v1/videos/${encodeURIComponent(videoId)}/reanalyse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Only the API's own field; an empty note is left out.
      body: JSON.stringify(note ? { reason: note } : {}),
    });
    if (res.status === 202 || res.ok) {
      const body = (await res.json()) as { job_id: string; reanalyses_remaining?: number };
      return { ok: true, jobId: body.job_id, remaining: body.reanalyses_remaining ?? null };
    }
    const detail = await detailOf(res);
    const code = detail && typeof detail === "object" ? (detail as { code?: string }).code : undefined;
    if (res.status === 429) return { ok: false, message: rateLimitMessage(detail as RateLimitDetail, res.headers.get("Retry-After")) };
    if (res.status === 403 && code === "REANALYSIS_DISABLED") return { ok: false, message: "Re-analysis is turned off at the moment." };
    if (res.status === 403) return { ok: false, message: "Only the person who submitted this video, or an admin, can re-analyse it." };
    if (res.status === 404) return { ok: false, message: "We can't find this video any more." };
    if (res.status === 422) return { ok: false, message: `Keep the reason under ${REANALYSE_REASON_MAX} characters.` };
    return { ok: false, message: "The re-analysis couldn't be started. Try again in a moment." };
  } catch {
    return { ok: false, message: "The re-analysis couldn't be started: no connection." };
  }
}
