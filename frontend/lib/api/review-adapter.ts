// ADAPTER: the review API (T27, T33, T34) → what the queue and workspace render.
import { reasonCodeText, type PreReveal } from "@/lib/review/decision";
import {
  isSeverity,
  isStance,
  isVerdict,
  isVideoLabel,
  reasonRule,
  reasonText,
  SEVERITY,
  type Severity,
  type Stance,
  type Verdict,
  type VideoLabel,
} from "@/lib/vocabulary";
import { isOwnSubmission, submitterText } from "./owner";
import type { RawAudit, RawCase, RawCaseClaim, RawDecision, RawPreReveal, RawQueueItem } from "./review-types";

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
  /** T34: an open HIGH case that needs each reviewer's own judgement first. */
  blindRequired: boolean;
  /** T34: the server is withholding the system's view until this reviewer gives theirs. */
  withheld: boolean;
  decision: Decision | null;
};

export type Decision = {
  action: string;
  actionText: string;
  by: string;
  /** T34 reason code and its text; read from a pre-T34 "[CODE] note" when absent. */
  reasonCode: string | null;
  reasonCodeText: string | null;
  /** The written note. */
  reason: string;
  correctedLabel: VideoLabel | null;
  at: string | null;
};

export type AuditItem = { id: string; when: string; who: string; what: string; reason: string | null };

/** T34: a claim as the case lists it. `stance` / `verdict` are the system's, null while withheld. */
export type CaseClaim = { id: string; number: number; text: string; start: number | null; end: number | null; stance: Stance | null; verdict: Verdict | null };

export type CaseModel = QueueItem & {
  /** Every claim of the case: the blind step asks for a judgement on each. */
  claims: CaseClaim[];
  /** The caller's own blind judgement, as the server recorded it. */
  myPreReveal: PreReveal[] | null;
  audit: AuditItem[];
};

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

/** Decisions saved before T34 folded the code into the note: "[EVIDENCE_MISREAD] The trial…". */
export function splitReason(code: string | null | undefined, reason: string | null | undefined): { code: string | null; note: string } {
  const text = reason ?? "";
  if (code) return { code, note: text };
  const m = /^\[([A-Z_]+)\]\s*([\s\S]*)$/.exec(text);
  return m && reasonCodeText(m[1]) ? { code: m[1], note: m[2] } : { code: null, note: text };
}

function decision(d: RawDecision | null | undefined): Decision | null {
  if (!d) return null;
  const { code, note } = splitReason(d.reason_code, d.reason);
  return {
    action: d.action,
    actionText: ACTION_TEXT[d.action] ?? "Decided",
    by: personName(d.reviewer_name, d.reviewer_id),
    reasonCode: code,
    reasonCodeText: reasonCodeText(code),
    reason: note,
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

/** `viewerId`: the signed-in user, to mark their own submissions until T34 sends `is_own`. */
export function adaptQueueItem(r: RawQueueItem, viewerId: string | null = null): QueueItem {
  const isOwn = isOwnSubmission(r.submitted_by, viewerId, r.is_own);
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
    submittedBy: submitterText(r.submitted_by, isOwn, r.submitted_by_name),
    isOwn,
    blindRequired: r.blind_step_required ?? false,
    withheld: r.system_view_withheld ?? false,
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

function caseClaim(c: RawCaseClaim, i: number): CaseClaim {
  return {
    id: c.claim_id,
    number: i + 1,
    text: c.text ?? "",
    start: c.start ?? null,
    end: c.end ?? null,
    stance: isStance(c.stance) ? c.stance : null,
    verdict: isVerdict(c.verdict) ? c.verdict : null,
  };
}

function preReveal(p: RawPreReveal | null | undefined): PreReveal[] | null {
  if (!p) return null;
  const out: PreReveal[] = [];
  for (const [claimId, v] of Object.entries(p.claims ?? {})) {
    if (isStance(v.stance) && isVerdict(v.verdict)) out.push({ claimId, stance: v.stance, verdict: v.verdict });
  }
  return out.length ? out : null;
}

export function adaptCase(r: RawCase, viewerId: string | null = null): CaseModel {
  return {
    ...adaptQueueItem(r, viewerId),
    claims: (r.claims ?? []).map(caseClaim),
    myPreReveal: preReveal(r.pre_reveal),
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
