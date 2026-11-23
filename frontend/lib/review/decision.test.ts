import { describe, expect, it } from "vitest";
import {
  decisionRequest,
  disagreements,
  EMPTY_FORM,
  isValid,
  mismatchWarning,
  needsBlindStep,
  validateDecision,
  type DecisionContext,
  type DecisionForm,
} from "./decision";

const ctx: DecisionContext = { proposedLabel: "MISINFO", severity: "MEDIUM", preReveal: null, isOwnSubmission: false, alreadyDecided: false };
const ok: DecisionForm = { kind: "APPROVE", correctedLabel: null, reasonCode: "SYSTEM_CORRECT", note: "Checked both sources; label holds.", claimCorrections: [] };

describe("validateDecision", () => {
  it("accepts a complete approval", () => {
    expect(validateDecision(ok, ctx)).toEqual({});
  });

  it("requires a decision, a reason code and a note on an empty form", () => {
    const e = validateDecision(EMPTY_FORM, ctx);
    expect(Object.keys(e).sort()).toEqual(["kind", "note", "reasonCode"]);
  });

  it.each(["APPROVE", "CORRECT", "REJECT", "REQUEST_REANALYSIS"] as const)("requires a reason for %s", (kind) => {
    const e = validateDecision({ ...ok, kind, correctedLabel: "DEBUNKING", reasonCode: null, note: "" }, ctx);
    expect(e.reasonCode).toBeDefined();
    expect(e.note).toBeDefined();
  });

  it("requires a note of at least 10 characters, ignoring surrounding spaces", () => {
    expect(validateDecision({ ...ok, note: "  too short " }, ctx).note).toMatch(/at least 10/);
    expect(validateDecision({ ...ok, note: "exactly 10" }, ctx).note).toBeUndefined();
  });

  it("rejects a note over the server's limit", () => {
    expect(validateDecision({ ...ok, note: "x".repeat(4001) }, ctx).note).toMatch(/under 4000/);
  });

  it("requires a new label to correct", () => {
    expect(validateDecision({ ...ok, kind: "CORRECT" }, ctx).correctedLabel).toMatch(/Choose the corrected label/);
  });

  it("doesn't accept a 'correction' to the same label with nothing else changed", () => {
    expect(validateDecision({ ...ok, kind: "CORRECT", correctedLabel: "MISINFO" }, ctx).correctedLabel).toMatch(/system's label/);
    const withClaimFix = { ...ok, kind: "CORRECT" as const, correctedLabel: "MISINFO" as const, claimCorrections: [{ claimId: "c1", verdict: "UNSUPPORTED" as const }] };
    expect(validateDecision(withClaimFix, ctx).correctedLabel).toBeUndefined();
  });

  it("requires the reviewer's own judgement first on HIGH cases only", () => {
    expect(needsBlindStep({ severity: "HIGH" })).toBe(true);
    expect(needsBlindStep({ severity: "MEDIUM" })).toBe(false);
    expect(validateDecision(ok, { ...ctx, severity: "HIGH" }).preReveal).toBeDefined();
    expect(validateDecision(ok, { ...ctx, severity: "HIGH", preReveal: [{ claimId: "c1", stance: "ENDORSES", verdict: "CONTRADICTED" }] })).toEqual({});
  });

  it("blocks deciding your own submission and an already decided case", () => {
    expect(validateDecision(ok, { ...ctx, isOwnSubmission: true }).form).toMatch(/Another reviewer decides/);
    expect(validateDecision(ok, { ...ctx, alreadyDecided: true }).form).toMatch(/already been decided/);
    expect(isValid(validateDecision(ok, { ...ctx, alreadyDecided: true }))).toBe(false);
  });
});

describe("mismatchWarning", () => {
  it("warns, without blocking, when the chosen label doesn't follow from the claims", () => {
    const f = { ...ok, kind: "CORRECT" as const, correctedLabel: "NO_MISINFO" as const };
    expect(mismatchWarning(f, "DEBUNKING")).toMatch(/doesn't follow/);
    expect(mismatchWarning(f, "NO_MISINFO")).toBeNull();
    expect(mismatchWarning(ok, "DEBUNKING")).toBeNull();
    expect(isValid(validateDecision(f, ctx))).toBe(true);
  });
});

describe("disagreements", () => {
  it("lists where the reviewer and the system differ", () => {
    const mine = [
      { claimId: "c1", stance: "REFUTES" as const, verdict: "CONTRADICTED" as const },
      { claimId: "c2", stance: "ENDORSES" as const, verdict: "SUPPORTED" as const },
    ];
    const system = [
      { claimId: "c1", stance: "REFUTES" as const, verdict: "INSUFFICIENT_EVIDENCE" as const },
      { claimId: "c2", stance: "ENDORSES" as const, verdict: "SUPPORTED" as const },
    ];
    expect(disagreements(mine, system)).toEqual([{ claimId: "c1", stance: false, verdict: true }]);
  });
});

describe("decisionRequest", () => {
  it("builds T27's DecisionRequest with nothing T27 would reject", () => {
    const { body } = decisionRequest(
      { kind: "CORRECT", correctedLabel: "DEBUNKING", reasonCode: "EVIDENCE_MISREAD", note: "  The trial contradicts it.  ", claimCorrections: [{ claimId: "c1", verdict: "CONTRADICTED" }, { claimId: "c2" }] },
      null,
    );
    expect(body).toEqual({
      action: "CORRECT",
      reason: "[EVIDENCE_MISREAD] The trial contradicts it.",
      corrected_label: "DEBUNKING",
      claim_corrections: [{ claim_id: "c1", verdict: "CONTRADICTED" }],
    });
    expect(Object.keys(body).sort()).toEqual(["action", "claim_corrections", "corrected_label", "reason"]);
  });

  it("drops the label and claim edits for other decisions", () => {
    const { body } = decisionRequest({ ...ok, correctedLabel: "DEBUNKING", claimCorrections: [{ claimId: "c1", verdict: "SUPPORTED" }] }, null);
    expect(body.corrected_label).toBeNull();
    expect(body.claim_corrections).toEqual([]);
  });

  it("keeps the proposed fields apart from the body", () => {
    const pre = [{ claimId: "c1", stance: "REFUTES" as const, verdict: "CONTRADICTED" as const }];
    const { proposed } = decisionRequest(ok, pre);
    expect(proposed).toEqual({ reason_code: "SYSTEM_CORRECT", reason_text: "The system's assessment is right", pre_reveal: pre });
  });
});

import { labelFromClaims } from "./decision";

describe("labelFromClaims (warning only)", () => {
  it.each([
    [[{ stance: "ENDORSES", verdict: "CONTRADICTED" }], "MISINFO"],
    [[{ stance: "ENDORSES", verdict: "UNSUPPORTED" }], "MISINFO"],
    [[{ stance: "REFUTES", verdict: "SUPPORTED" }], "MISINFO"],
    [[{ stance: "REFUTES", verdict: "CONTRADICTED" }], "DEBUNKING"],
    [[{ stance: "REFUTES", verdict: "CONTRADICTED" }, { stance: "ENDORSES", verdict: "CONTRADICTED" }], "MISINFO"],
    [[{ stance: "ENDORSES", verdict: "SUPPORTED" }], "NO_MISINFO"],
    [[{ stance: "REFUTES", verdict: "INSUFFICIENT_EVIDENCE" }], "CANNOT_RECOGNIZE"],
    [[], "CANNOT_RECOGNIZE"],
  ] as const)("%j → %s", (claims, label) => {
    expect(labelFromClaims(claims as never)).toBe(label);
  });
});
