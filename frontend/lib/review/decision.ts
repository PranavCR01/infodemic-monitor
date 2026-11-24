// Review decision form: rules and request body (HANDOFF §6.8; lead decisions Q1, Q2).
// Pure functions, so every rule is unit-tested. The server (T27, T34) checks again;
// these rules decide what the form allows, they are not the control.

import type { Stance, Verdict, VideoLabel } from "@/lib/vocabulary";

export type DecisionKind = "APPROVE" | "CORRECT" | "REJECT" | "REQUEST_REANALYSIS";

export const DECISIONS: { kind: DecisionKind; title: string; description: string; submit: string }[] = [
  { kind: "APPROVE", title: "Approve the label", description: "The system's label becomes final.", submit: "Approve label" },
  { kind: "CORRECT", title: "Correct it", description: "Choose a new label; optionally fix claim stances or verdicts.", submit: "Save correction" },
  { kind: "REJECT", title: "Reject the result", description: "The analysis is unusable (wrong video, bad audio). No label is kept.", submit: "Reject result" },
  { kind: "REQUEST_REANALYSIS", title: "Request re-analysis", description: "Run the analysis again. The item leaves the queue until it returns.", submit: "Request re-analysis" },
];

/** Reason codes (Q2, D7): T34's `reason_code` enum, sent next to the written note. */
export const REASON_CODES = [
  { code: "SYSTEM_CORRECT", text: "The system's assessment is right" },
  { code: "CLAIM_OVERGENERALISED", text: "Claim is an overgeneralisation the evidence rules out" },
  { code: "EVIDENCE_MISREAD", text: "Evidence misread by the system" },
  { code: "STANCE_MISREAD", text: "Stance misread by the system" },
  { code: "MISSING_SOURCE", text: "A relevant source is missing" },
  { code: "OTHER", text: "Other (explain in the note)" },
] as const;
export type ReasonCode = (typeof REASON_CODES)[number]["code"];

export const NOTE_MIN = 10;
export const NOTE_MAX = 4000;

export type ClaimCorrection = { claimId: string; stance?: Stance; verdict?: Verdict };
export type PreReveal = { claimId: string; stance: Stance; verdict: Verdict };

export type DecisionForm = {
  kind: DecisionKind | null;
  correctedLabel: VideoLabel | null;
  reasonCode: ReasonCode | null;
  note: string;
  claimCorrections: ClaimCorrection[];
};

export const EMPTY_FORM: DecisionForm = { kind: null, correctedLabel: null, reasonCode: null, note: "", claimCorrections: [] };

export type DecisionContext = {
  proposedLabel: VideoLabel | null;
  /** T34: the server says this case needs the reviewer's own judgement first (open HIGH). */
  blindRequired: boolean;
  /** The reviewer's own judgement, as the server recorded it (Q1). */
  preReveal: PreReveal[] | null;
  isOwnSubmission: boolean;
  alreadyDecided: boolean;
};

export type FieldErrors = Partial<Record<"kind" | "correctedLabel" | "reasonCode" | "note" | "preReveal" | "form", string>>;


export function validateDecision(f: DecisionForm, ctx: DecisionContext): FieldErrors {
  const e: FieldErrors = {};
  if (ctx.alreadyDecided) e.form = "This case has already been decided.";
  else if (ctx.isOwnSubmission) e.form = "You submitted this video. Another reviewer decides.";
  if (ctx.blindRequired && !ctx.preReveal?.length) e.preReveal = "Record your own judgement first.";
  if (!f.kind) e.kind = "Choose a decision.";
  if (f.kind === "CORRECT") {
    if (!f.correctedLabel) e.correctedLabel = "Choose the corrected label.";
    else if (f.correctedLabel === ctx.proposedLabel && f.claimCorrections.length === 0) {
      e.correctedLabel = "This is the system's label. Choose a different label, correct a claim, or approve instead.";
    }
  }
  if (!f.reasonCode) e.reasonCode = "Choose a reason.";
  else if (f.reasonCode === "SYSTEM_CORRECT" && f.kind && f.kind !== "APPROVE") {
    // T34: the server accepts SYSTEM_CORRECT only with APPROVE.
    e.reasonCode = "\"The system's assessment is right\" goes only with Approve. Choose another reason.";
  }
  const note = f.note.trim();
  if (note.length < NOTE_MIN) e.note = `Write at least ${NOTE_MIN} characters explaining your decision.`;
  else if (note.length > NOTE_MAX) e.note = `Keep the note under ${NOTE_MAX} characters.`;
  return e;
}

export const isValid = (e: FieldErrors) => Object.keys(e).length === 0;

/**
 * Non-blocking warning (HANDOFF §6.8): correcting claims doesn't recompute the label,
 * so say when the chosen label no longer follows from the claims.
 */
export function mismatchWarning(f: DecisionForm, labelFromClaims: VideoLabel | null): string | null {
  if (f.kind !== "CORRECT" || !f.correctedLabel || !labelFromClaims) return null;
  if (f.correctedLabel === labelFromClaims) return null;
  return "The label you chose doesn't follow from the claims as they now stand. It will be saved as you chose; check that's what you mean.";
}

/**
 * The label the judge's rules (§9) would give these claims, for the mismatch
 * warning only. A simplified mirror of backend/app/core/graph/judge.py; the server
 * never uses it, and the reviewer's chosen label is always what is saved.
 */
export function labelFromClaims(claims: { stance: Stance | null; verdict: Verdict | null }[]): VideoLabel {
  const has = (st: Stance, v: Verdict) => claims.some((c) => c.stance === st && c.verdict === v);
  if (has("ENDORSES", "CONTRADICTED") || has("REFUTES", "SUPPORTED") || has("ENDORSES", "UNSUPPORTED")) return "MISINFO";
  if (has("REFUTES", "CONTRADICTED")) return "DEBUNKING";
  if (claims.some((c) => c.verdict === "SUPPORTED" || c.verdict === "CONTRADICTED")) return "NO_MISINFO";
  return "CANNOT_RECOGNIZE";
}

/** Where the reviewer and the system disagree (HIGH cases, after the reveal). */
export function disagreements(
  mine: PreReveal[],
  system: { claimId: string; stance: Stance | null; verdict: Verdict | null }[],
): { claimId: string; stance: boolean; verdict: boolean }[] {
  return mine
    .map((m) => {
      const s = system.find((x) => x.claimId === m.claimId);
      return { claimId: m.claimId, stance: !!s && s.stance !== m.stance, verdict: !!s && s.verdict !== m.verdict };
    })
    .filter((d) => d.stance || d.verdict);
}

/** Body for POST /v1/reviews/{id}/decision: T34's DecisionRequest (extra fields are forbidden). */
export function decisionRequest(f: DecisionForm) {
  const body = {
    action: f.kind as DecisionKind,
    reason: f.note.trim(),
    reason_code: f.reasonCode as ReasonCode,
    corrected_label: f.kind === "CORRECT" ? f.correctedLabel : null,
    claim_corrections:
      f.kind === "CORRECT"
        ? f.claimCorrections
            .filter((c) => c.stance || c.verdict)
            .map((c) => ({ claim_id: c.claimId, ...(c.stance ? { stance: c.stance } : {}), ...(c.verdict ? { verdict: c.verdict } : {}) }))
        : [],
  };
  return { body };
}

/** Body for POST /v1/reviews/{id}/pre-reveal (T34): a stance and verdict for every claim. */
export function preRevealRequest(mine: PreReveal[], note?: string) {
  const n = note?.trim();
  return {
    claims: mine.map((m) => ({ claim_id: m.claimId, stance: m.stance, verdict: m.verdict })),
    ...(n ? { note: n } : {}),
  };
}

/** Text for a reason code, or null for an unknown one. */
export const reasonCodeText = (code: string | null | undefined): string | null =>
  REASON_CODES.find((r) => r.code === code)?.text ?? null;
