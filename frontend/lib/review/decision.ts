// Review decision form: rules and request body (HANDOFF §6.8; lead decisions Q1, Q2).
// Pure functions, so every rule is unit-tested. The server (T27) checks again;
// these rules decide what the form allows, they are not the control.

import type { Severity, Stance, Verdict, VideoLabel } from "@/lib/vocabulary";

export type DecisionKind = "APPROVE" | "CORRECT" | "REJECT" | "REQUEST_REANALYSIS";

export const DECISIONS: { kind: DecisionKind; title: string; description: string; submit: string }[] = [
  { kind: "APPROVE", title: "Approve the label", description: "The system's label becomes final.", submit: "Approve label" },
  { kind: "CORRECT", title: "Correct it", description: "Choose a new label; optionally fix claim stances or verdicts.", submit: "Save correction" },
  { kind: "REJECT", title: "Reject the result", description: "The analysis is unusable (wrong video, bad audio). No label is kept.", submit: "Reject result" },
  { kind: "REQUEST_REANALYSIS", title: "Request re-analysis", description: "Run the analysis again. The item leaves the queue until it returns.", submit: "Request re-analysis" },
];

/**
 * Reason codes (Q2: a code and a note on every decision). PROPOSED to T27; the API
 * today takes only a free-text reason, so the adapter folds the code into it.
 */
export const REASON_CODES = [
  { code: "SYSTEM_CORRECT", text: "The system's assessment is right" },
  { code: "CLAIM_OVERGENERALISED", text: "Claim is an overgeneralisation the evidence rules out" },
  { code: "EVIDENCE_MISREAD", text: "Evidence misread by the system" },
  { code: "STANCE_MISREAD", text: "Stance misread by the system" },
  { code: "MISSING_SOURCE", text: "A relevant source is missing" },
  { code: "UNUSABLE_INPUT", text: "The video or audio can't be analysed" },
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
  severity: Severity | null;
  /** HIGH cases: the reviewer's own judgement, committed before the reveal (Q1). */
  preReveal: PreReveal[] | null;
  isOwnSubmission: boolean;
  alreadyDecided: boolean;
};

export type FieldErrors = Partial<Record<"kind" | "correctedLabel" | "reasonCode" | "note" | "preReveal" | "form", string>>;

/** Whether the blind first step applies (Q1: HIGH only). */
export const needsBlindStep = (ctx: Pick<DecisionContext, "severity">) => ctx.severity === "HIGH";

export function validateDecision(f: DecisionForm, ctx: DecisionContext): FieldErrors {
  const e: FieldErrors = {};
  if (ctx.alreadyDecided) e.form = "This case has already been decided.";
  else if (ctx.isOwnSubmission) e.form = "You submitted this video. Another reviewer decides.";
  if (needsBlindStep(ctx) && !ctx.preReveal?.length) e.preReveal = "Record your own judgement first.";
  if (!f.kind) e.kind = "Choose a decision.";
  if (f.kind === "CORRECT") {
    if (!f.correctedLabel) e.correctedLabel = "Choose the corrected label.";
    else if (f.correctedLabel === ctx.proposedLabel && f.claimCorrections.length === 0) {
      e.correctedLabel = "This is the system's label. Choose a different label, correct a claim, or approve instead.";
    }
  }
  if (!f.reasonCode) e.reasonCode = "Choose a reason.";
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

/**
 * Body for POST /v1/reviews/{id}/decision, exactly T27's DecisionRequest. T27 forbids
 * unknown fields, so the proposed reason_code / pre_reveal are returned separately
 * (`proposed`) and are only sent once the API accepts them.
 */
export function decisionRequest(f: DecisionForm, preReveal: PreReveal[] | null) {
  const code = REASON_CODES.find((r) => r.code === f.reasonCode);
  const body = {
    action: f.kind as DecisionKind,
    // One string today: the code first, so it can be found in the audit trail.
    reason: `[${f.reasonCode}] ${f.note.trim()}`,
    corrected_label: f.kind === "CORRECT" ? f.correctedLabel : null,
    claim_corrections:
      f.kind === "CORRECT"
        ? f.claimCorrections
            .filter((c) => c.stance || c.verdict)
            .map((c) => ({ claim_id: c.claimId, ...(c.stance ? { stance: c.stance } : {}), ...(c.verdict ? { verdict: c.verdict } : {}) }))
        : [],
  };
  return { body, proposed: { reason_code: f.reasonCode, reason_text: code?.text ?? null, pre_reveal: preReveal } };
}
