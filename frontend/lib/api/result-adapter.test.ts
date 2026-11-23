import { describe, expect, it } from "vitest";
import { EVIDENCE_LEVEL_DISPLAY } from "@/lib/vocabulary";
import { adaptResult, claimAt, claimsForSegment, clock, evidenceText } from "./result-adapter";
import { MOCK_DEBUNKED_VERIFIED, MOCK_LEGACY, MOCK_MISINFO_PENDING, MOCK_NO_CLAIMS, MOCK_UNPROVEN } from "./mocks/results";

describe("adaptResult: labels and review status", () => {
  it("reads a pending MISINFO case", () => {
    const r = adaptResult(MOCK_MISINFO_PENDING);
    expect(r.label).toBe("MISINFO");
    expect(r.basis).toBe("contradicted");
    expect(r.reviewStatus).toBe("PENDING");
    expect(r.reviewSeverity).toBe("HIGH");
    expect(r.decidingClaims.map((c) => c.number)).toEqual([1]);
  });

  it("reads a verified DEBUNKED case", () => {
    const r = adaptResult(MOCK_DEBUNKED_VERIFIED);
    expect(r.label).toBe("DEBUNKING");
    expect(r.reviewStatus).toBe("VERIFIED");
    expect(r.reviewDecidedAt).toBe("2026-11-22T16:40:00Z");
  });

  it("keeps the unproven basis only on MISINFO", () => {
    expect(adaptResult(MOCK_UNPROVEN).basis).toBe("unproven");
    expect(adaptResult({ ...MOCK_DEBUNKED_VERIFIED, misinfo_basis: "unproven" }).basis).toBeNull();
    expect(adaptResult({ ...MOCK_UNPROVEN, misinfo_basis: "nonsense" }).basis).toBeNull();
  });

  it("says 'Not required' when a finished job has no review case", () => {
    expect(adaptResult(MOCK_NO_CLAIMS).reviewStatus).toBe("NOT_REQUIRED");
  });

  it("treats today's REVIEW_REQUIRED job without T26 fields as pending", () => {
    expect(adaptResult({ ...MOCK_LEGACY, status: "REVIEW_REQUIRED", review: undefined }).reviewStatus).toBe("PENDING");
  });

  it("maps T26's resolved statuses", () => {
    const base = MOCK_MISINFO_PENDING.review!;
    const status = (s: string) => adaptResult({ ...MOCK_MISINFO_PENDING, review: { ...base, status: s } }).reviewStatus;
    expect(status("CORRECTED")).toBe("CORRECTED");
    expect(status("REJECTED")).toBe("REJECTED");
    expect(status("REANALYSIS_REQUESTED")).toBe("REANALYSIS");
  });

  it("shows the reviewer's label after a correction", () => {
    const r = adaptResult({
      ...MOCK_MISINFO_PENDING,
      review: { ...MOCK_MISINFO_PENDING.review!, status: "CORRECTED", corrected_label: "CANNOT_RECOGNIZE" },
    });
    expect(r.correctedLabel).toBe("CANNOT_RECOGNIZE");
  });

  it("returns a null label for an unknown value instead of passing it through", () => {
    expect(adaptResult({ ...MOCK_LEGACY, label: "SOMETHING_ELSE" }).label).toBeNull();
  });
});

describe("adaptResult: text never shows internal names", () => {
  it("strips the enum prefix from the template explanation", () => {
    expect(adaptResult(MOCK_NO_CLAIMS).explanation).toBe("CANNOT RECOGNIZE: no checkable health claims were found in the video.");
  });

  it("replaces reason text that names internal claim ids, and numbers the claim instead", () => {
    const r = adaptResult(MOCK_MISINFO_PENDING);
    for (const reason of r.reasons) expect(reason.text).not.toMatch(/\bc\d\b/);
    expect(r.reasons.map((x) => x.claimNumber)).toEqual([3, 1]);
  });

  it("uses the vocabulary when the API's reason text is empty", () => {
    expect(adaptResult(MOCK_UNPROVEN).reasons[0].text).toMatch(/no evidence supports it/);
  });

  it("falls back to the stored reason strings before T26", () => {
    const r = adaptResult({ ...MOCK_MISINFO_PENDING, review: { status: "REVIEW_REQUIRED", reasons: ["weak_evidence:c3"] } });
    expect(r.reasons).toEqual([{ code: "weak_evidence:c3", claimNumber: 3, text: expect.stringMatching(/too weak/) }]);
  });

  it("hides a generic text that prints a rule code", () => {
    const r = adaptResult({
      ...MOCK_MISINFO_PENDING,
      review: { ...MOCK_MISINFO_PENDING.review!, reason_details: [{ code: "new_rule", rule: "other", text: "Flagged for review by rule 'new_rule'.", raw: "new_rule" }] },
    });
    expect(r.reasons[0].text).not.toContain("new_rule");
  });
});

describe("adaptResult: claims, evidence and transcript", () => {
  const r = adaptResult(MOCK_MISINFO_PENDING);

  it("numbers claims in time order", () => {
    const shuffled = adaptResult({ ...MOCK_MISINFO_PENDING, claims: [...MOCK_MISINFO_PENDING.claims!].reverse() });
    expect(shuffled.claims.map((c) => [c.number, c.id])).toEqual([[1, "c1"], [2, "c2"], [3, "c3"]]);
  });

  it("summarises evidence by level and direction", () => {
    const c1 = r.claims[0];
    expect(c1.evidence.contradicts).toBe(2);
    expect(c1.evidence.levels).toEqual([{ level: "RCT", direction: "contradicts", count: 1 }]);
    expect(c1.evidence.guidance).toEqual([{ direction: "contradicts", count: 1 }]);
    expect(evidenceText(c1.evidence, EVIDENCE_LEVEL_DISPLAY)).toBe("1 randomised trial against · official guidance against");
  });

  it("says plainly when no source tests a claim", () => {
    expect(evidenceText(r.claims[2].evidence, EVIDENCE_LEVEL_DISPLAY)).toBe("No source found that tests this claim");
  });

  it("never links internal library documents", () => {
    const lib = adaptResult({
      ...MOCK_MISINFO_PENDING,
      claims: [{ ...MOCK_MISINFO_PENDING.claims![0], evidence: [{ evidence_id: "x", title: "t", relation: "SUPPORTS", source_kind: "library", url: "https://internal" }] }],
    });
    expect(lib.claims[0].sources[0].url).toBeNull();
  });

  it("links PubMed when only a PMID is given", () => {
    expect(r.claims[0].sources[0].url).toBe("https://pubmed.ncbi.nlm.nih.gov/00000001/");
  });

  it("merges speech and on-screen text in time order", () => {
    expect(r.transcript.map((s) => s.id)).toEqual(["t1", "t2", "o1", "t3", "t4", "o2", "t5"]);
  });

  it("finds the claim at a moment and the claims behind a segment", () => {
    expect(claimAt(r.claims, 5)?.number).toBe(1);
    expect(claimAt(r.claims, 21)).toBeNull();
    // c1 ends at 8.1 where c2 starts: the boundary belongs to the claim that starts there
    expect(claimAt(r.claims, 8.1)?.number).toBe(2);
    expect(claimAt(r.claims, 19.0)?.number).toBe(3); // end of the last claim
    expect(claimsForSegment(r.claims, r.transcript[2]).map((c) => c.number)).toEqual([1]);
  });

  it("works with today's API (no claim-level data)", () => {
    const legacy = adaptResult(MOCK_LEGACY);
    expect(legacy.hasClaimLevel).toBe(false);
    expect(legacy.transcript).toEqual([]);
    expect(legacy.reasons).toEqual([]);
    expect(legacy.search).toBeNull();
  });
});

describe("clock", () => {
  it.each([
    [0, "0:00"],
    [3.2, "0:03"],
    [65, "1:05"],
    [-1, "0:00"],
  ])("%s → %s", (s, out) => expect(clock(s)).toBe(out));
});
