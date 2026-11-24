// Review API calls (T27, #78). Every call goes through the adapter.
import { apiFetch } from "@/lib/api";
import type { SubmitResult } from "@/components/review/ReviewWorkspace";
import { adaptCase, adaptQueueItem, type CaseModel, type QueueItem } from "./review-adapter";
import type { RawCase, RawQueuePage } from "./review-types";
import type { decisionRequest } from "@/lib/review/decision";

export type Loaded<T> = { ok: true; data: T } | { ok: false; status: number; message: string };

function failure(status: number): Loaded<never> {
  const message =
    status === 403
      ? "You don't have access to the review queue."
      : status === 404
        ? "We can't find that review."
        : "The review service isn't available right now. Try again in a moment.";
  return { ok: false, status, message };
}

export async function fetchQueue(view: "open" | "decided"): Promise<Loaded<{ items: QueueItem[]; total: number }>> {
  try {
    const res = await apiFetch(`/v1/reviews?status=${view === "open" ? "OPEN" : "RESOLVED"}&limit=100`);
    if (!res.ok) return failure(res.status);
    const page: RawQueuePage = await res.json();
    return { ok: true, data: { items: page.items.map(adaptQueueItem), total: page.total } };
  } catch {
    return failure(0);
  }
}

export async function fetchCase(id: string): Promise<Loaded<CaseModel>> {
  try {
    const res = await apiFetch(`/v1/reviews/${encodeURIComponent(id)}`);
    if (!res.ok) return failure(res.status);
    return { ok: true, data: adaptCase((await res.json()) as RawCase) };
  } catch {
    return failure(0);
  }
}

const DECISION_ERRORS: Record<number, string> = {
  409: "Someone else decided this case while you were working on it. Reload to see their decision.",
  403: "You can't decide this case.",
  422: "The decision wasn't accepted. Check the form and try again.",
};

export async function postDecision(id: string, req: ReturnType<typeof decisionRequest>): Promise<SubmitResult> {
  try {
    // Only T27's own fields: it forbids extra ones. `req.proposed` waits for the API.
    const res = await apiFetch(`/v1/reviews/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    if (res.ok) return { ok: true };
    return { ok: false, message: DECISION_ERRORS[res.status] ?? "The decision couldn't be saved. Try again." };
  } catch {
    return { ok: false, message: "The decision couldn't be saved: no connection. Your form is still here." };
  }
}

export async function postSeverity(id: string, claimId: string, severity: string, reason: string): Promise<SubmitResult> {
  try {
    const res = await apiFetch(`/v1/reviews/${encodeURIComponent(id)}/claims/${encodeURIComponent(claimId)}/severity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ severity, reason }),
    });
    if (res.ok) return { ok: true };
    return { ok: false, message: res.status === 409 ? "That claim already has this priority." : "The priority couldn't be changed. Try again." };
  } catch {
    return { ok: false, message: "The priority couldn't be changed: no connection." };
  }
}
