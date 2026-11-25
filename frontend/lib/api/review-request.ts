// T32 (#83): POST /v1/jobs/{job_id}/review-request {note} → opens a review case
// for a result the review rule didn't send to review (or returns the existing one).
import { apiFetch } from "@/lib/api";

export const REQUEST_NOTE_MAX = 2000;

export type RequestOutcome = { ok: true; created: boolean } | { ok: false; message: string };

export function requestNoteProblem(note: string): string | null {
  const n = note.trim();
  if (!n) return "Say what looks wrong, so the reviewer knows where to look.";
  if (n.length > REQUEST_NOTE_MAX) return `Keep the note under ${REQUEST_NOTE_MAX} characters.`;
  return null;
}

export async function requestReview(jobId: string, note: string): Promise<RequestOutcome> {
  try {
    const res = await apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}/review-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: note.trim() }),
    });
    if (res.status === 201 || res.status === 200) {
      const body = (await res.json()) as { created?: boolean };
      return { ok: true, created: Boolean(body.created) };
    }
    if (res.status === 409) return { ok: false, message: "A review can be requested once the analysis has finished." };
    if (res.status === 404) return { ok: false, message: "We can't find this video any more." };
    return { ok: false, message: "The request couldn't be sent. Try again in a moment." };
  } catch {
    return { ok: false, message: "The request couldn't be sent: no connection. Your note is still here." };
  }
}
