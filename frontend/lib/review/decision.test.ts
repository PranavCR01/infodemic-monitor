import { describe, expect, it } from "vitest";
import {
  decisionRequest,
  disagreements,
  EMPTY_FORM,
  isValid,
  mismatchWarning,
  preRevealRequest,
  reasonCodeText,
  validateDecision,
  type DecisionContext,
  type DecisionForm,
} from "./decision";

const ctx: DecisionContext = { proposedLabel: "MISINFO", blindRequired: false, preReveal: null, isOwnSubmission: false, alreadyDecided: false };
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

  it("requires the reviewer's own judgement first when the server says the case needs it (T34)", () => {
    expect(validateDecision(ok, ctx).preReveal).toBeUndefined();
    expect(validateDecision(ok, { ...ctx, blindRequired: true }).preReveal).toBeDefined();
    expect(validateDecision(ok, { ...ctx, blindRequired: true, preReveal: [{ claimId: "c1", stance: "ENDORSES", verdict: "CONTRADICTED" }] })).toEqual({});
  });

  it("allows 'The system's assessment is right' only with Approve, as the server does (T34)", () => {
    expect(validateDecision({ ...ok, kind: "REJECT" }, ctx).reasonCode).toMatch(/goes only with Approve/);
    expect(validateDecision({ ...ok, kind: "REQUEST_REANALYSIS" }, ctx).reasonCode).toMatch(/goes only with Approve/);
    expect(validateDecision(ok, ctx).reasonCode).toBeUndefined();
  });

  it("blocks deciding your own submission and an already decided case", () => {
    expect(validateDecision(ok, { ...ctx, isOwnSubmission: true }).form).toMatch(/Another reviewer decides/);
    expect(validateDecision(ok, { ...ctx, alreadyDecided: true }).form).toMatch(/already been decided/);
    expect(isValid(validateDecision(ok, { ...ctx, alreadyDecided: true }))).toBe(false);
  });
});

describe("mismatchWarning", () => {
  it("warns, without blocking, when the chosen label doesn't follow from the claims", () => {
    const f = { ...ok, kind: "CORRECT" as const, correctedLabel: "NO_MISINFO" as const, reasonCode: "EVIDENCE_MISREAD" as const };
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
  it("builds T34's DecisionRequest: the note and the reason code as separate fields", () => {
    const { body } = decisionRequest({
      kind: "CORRECT", correctedLabel: "DEBUNKING", reasonCode: "EVIDENCE_MISREAD", note: "  The trial contradicts it.  ",
      claimCorrections: [{ claimId: "c1", verdict: "CONTRADICTED" }, { claimId: "c2" }],
    });
    expect(body).toEqual({
      action: "CORRECT",
      reason: "The trial contradicts it.",
      reason_code: "EVIDENCE_MISREAD",
      corrected_label: "DEBUNKING",
      claim_corrections: [{ claim_id: "c1", verdict: "CONTRADICTED" }],
    });
    // The server forbids extra fields: nothing else may be sent.
    expect(Object.keys(body).sort()).toEqual(["action", "claim_corrections", "corrected_label", "reason", "reason_code"]);
  });

  it("drops the label and claim edits for other decisions", () => {
    const { body } = decisionRequest({ ...ok, correctedLabel: "DEBUNKING", claimCorrections: [{ claimId: "c1", verdict: "SUPPORTED" }] });
    expect(body.corrected_label).toBeNull();
    expect(body.claim_corrections).toEqual([]);
  });
});

describe("preRevealRequest", () => {
  it("builds T34's PreRevealRequest, with only the allowed fields", () => {
    const mine = [{ claimId: "c1", stance: "REFUTES" as const, verdict: "CONTRADICTED" as const }];
    expect(preRevealRequest(mine)).toEqual({ claims: [{ claim_id: "c1", stance: "REFUTES", verdict: "CONTRADICTED" }] });
    expect(preRevealRequest(mine, "  ")).not.toHaveProperty("note");
    expect(preRevealRequest(mine, " gut call ").note).toBe("gut call");
  });

  it("names each reason code in words", () => {
    expect(reasonCodeText("STANCE_MISREAD")).toBe("Stance misread by the system");
    expect(reasonCodeText("NOPE")).toBeNull();
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
