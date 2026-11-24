// ADAPTER: the review API (T27) → what the queue and workspace render.
import { isSeverity, isVideoLabel, reasonRule, reasonText, SEVERITY, type Severity, type VideoLabel } from "@/lib/vocabulary";
import type { RawAudit, RawCase, RawDecision, RawQueueItem } from "./review-types";

export type QueueItem = {
  reviewId: string;
  jobId: string;
  filename: string;
  open: boolean;
  severity: Severity | null;
  proposedLabel: VideoLabel | null;
  reasons: { rule: string; text: string }[];
  waiting: string;
  ageSeconds: number;
  submittedBy: string | null;
  isOwn: boolean;
  decision: Decision | null;
};

export type Decision = {
  action: string;
  actionText: string;
  by: string;
  reason: string;
  correctedLabel: VideoLabel | null;
  at: string | null;
};

export type AuditItem = { id: string; when: string; who: string; what: string; reason: string | null };

export type CaseModel = QueueItem & { audit: AuditItem[] };

const ACTION_TEXT: Record<string, string> = {
  APPROVE: "Approved",
  CORRECT: "Corrected",
  MARK_INSUFFICIENT: "Corrected to CANNOT RECOGNIZE",
  REJECT: "Rejected",
  REQUEST_REANALYSIS: "Requested re-analysis",
  severity_override: "Changed a claim's priority",
  review_opened: "Sent the case for review",
  reanalysis_started: "Started a new analysis",
};

/** "3 h", "2 d": how long a case has waited. */
export function waitingText(seconds: number): string {
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${Math.max(1, m)} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

/** A person, never a raw id: the proposed display name, else a short neutral label. */
function personName(name: string | null | undefined, id: string | null | undefined): string {
  if (name) return name;
  return id ? `Reviewer ${id.slice(0, 6)}` : "A reviewer";
}

function decision(d: RawDecision | null | undefined): Decision | null {
  if (!d) return null;
  return {
    action: d.action,
    actionText: ACTION_TEXT[d.action] ?? "Decided",
    by: personName(d.reviewer_name, d.reviewer_id),
    reason: d.reason ?? "",
    correctedLabel: isVideoLabel(d.corrected_label) ? d.corrected_label : null,
    at: d.decided_at ?? null,
  };
}

/** One chip per rule, in plain language (several claims can raise the same rule). */
function reasonChips(reasons: string[]): { rule: string; text: string }[] {
  const seen = new Map<string, string>();
  for (const r of reasons) {
    const rule = reasonRule(r);
    if (!seen.has(rule)) seen.set(rule, reasonText(r));
  }
  return Array.from(seen, ([rule, text]) => ({ rule, text }));
}

export function adaptQueueItem(r: RawQueueItem): QueueItem {
  return {
    reviewId: r.review_id,
    jobId: r.job_id,
    filename: r.filename ?? "Untitled video",
    open: r.status === "OPEN",
    severity: isSeverity(r.severity) ? r.severity : null,
    proposedLabel: isVideoLabel(r.proposed_label) ? r.proposed_label : null,
    reasons: reasonChips(r.reasons),
    waiting: waitingText(r.age_seconds),
    ageSeconds: r.age_seconds,
    submittedBy: r.submitted_by ?? null,
    isOwn: r.is_own ?? false,
    decision: decision(r.decision),
  };
}

function auditItem(a: RawAudit): AuditItem {
  return {
    id: a.id,
    when: a.created_at,
    who: personName(a.actor_name, a.actor_id),
    what: ACTION_TEXT[a.action] ?? "Updated the case",
    reason: a.reason ?? null,
  };
}

export function adaptCase(r: RawCase): CaseModel {
  return {
    ...adaptQueueItem(r),
    audit: [...(r.audit_trail ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at)).map(auditItem),
  };
}

/** Severity, then oldest first (§12). The server already sorts; this keeps mocks and pages consistent. */
export function sortQueue(items: QueueItem[]): QueueItem[] {
  const rank = (s: Severity | null) => (s ? SEVERITY[s].rank : 3);
  return [...items].sort((a, b) => rank(a.severity) - rank(b.severity) || b.ageSeconds - a.ageSeconds);
}

/** Reason filter buttons with counts, for the items on screen. */
export function reasonCounts(items: QueueItem[]): { rule: string; text: string; count: number }[] {
  const m = new Map<string, { text: string; count: number }>();
  for (const i of items) for (const r of i.reasons) m.set(r.rule, { text: r.text, count: (m.get(r.rule)?.count ?? 0) + 1 });
  return Array.from(m, ([rule, v]) => ({ rule, ...v })).sort((a, b) => b.count - a.count);
}
