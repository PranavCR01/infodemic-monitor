import { describe, expect, it } from "vitest";
import { adaptResult, type Claim, type ClaimSearch, type Source } from "@/lib/api/result-adapter";
import { MOCK_MISINFO_PENDING } from "@/lib/api/mocks/results";
import { flaggedClaimIds, searchFinding, unusedSources } from "./search-finding";

const base: ClaimSearch = {
  queries: [], rounds: [], sources: [], libraryUsed: false,
  retrieved: 0, screened: 0, kept: 0, roundsUsed: 1, roundsMax: 3, budgetExhausted: false, partial: false,
};
const q = (query: string, failed = false) => ({ query, results: failed ? null : 3, failed });
const src = (id: string, relation: Source["relation"]): Source => ({
  id, title: `Paper ${id}`, relation, studyType: "rct", level: "RCT", kind: "pubmed", year: 2020, publisher: null, snippet: "", url: `https://pubmed.ncbi.nlm.nih.gov/${id}/`, pmid: id, journal: null, pubDate: null,
});
const claim = (search: Partial<ClaimSearch>, sources: Source[] = [], verdict: Claim["verdict"] = "INSUFFICIENT_EVIDENCE"): Pick<Claim, "search" | "sources" | "verdict"> => ({
  search: { ...base, ...search },
  sources,
  verdict,
});
const round = (r: number, query: string, repeat = false) => ({ round: r, query, results: 3, failed: false, repeat });

describe("searchFinding (T52)", () => {
  it("says the claim couldn't be checked when the papers retrieved were all off-topic, counting distinct searches", () => {
    expect(searchFinding(claim({ queries: [q("a"), q("b")], retrieved: 3, screened: 3, kept: 0 }), true)).toBe(
      "No relevant study was found after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so this claim could not be checked and was sent to a reviewer.",
    );
  });

  it("covers sources that were checked but neither supported nor contradicted the claim", () => {
    expect(searchFinding(claim({ queries: [q("a")], retrieved: 5, screened: 4, kept: 2 }, [src("1", "CONSIDERED"), src("2", "CONSIDERED")]), false)).toBe(
      "No relevant study was found after 1 search. 2 sources were checked and none of them supported or contradicted the claim, so this claim could not be checked.",
    );
  });

  it("says nothing was found at all", () => {
    expect(searchFinding(claim({ queries: [q("a"), q("b")] }), false)).toBe("No study was found after 2 searches, so this claim could not be checked.");
  });

  it("reports what the checked sources showed", () => {
    const f = searchFinding(claim({ queries: [q("a"), q("b")], retrieved: 14, screened: 12, kept: 3 }, [src("1", "CONTRADICTS"), src("2", "CONTRADICTS"), src("3", "SUPPORTS")]), true);
    expect(f).toBe("3 sources were checked against this claim after 2 searches: 2 contradict it and 1 supports it. The claim was sent to a reviewer.");
  });

  it("says when every search failed", () => {
    expect(searchFinding(claim({ queries: [q("a", true), q("b", true)] }), false)).toBe(
      "The study search failed each time it ran (2 searches), so this claim could not be checked.",
    );
  });

  it("says all rounds were used only when that many distinct searches ran", () => {
    const three = claim({ queries: [q("a"), q("b"), q("c")], rounds: [round(1, "a"), round(2, "b"), round(3, "c")], roundsUsed: 3, budgetExhausted: true });
    expect(searchFinding(three, false)).toMatch(/after 3 searches, .* The search used all 3 rounds allowed for a claim\.$/);
  });

  it("doesn't overstate the effort when later rounds repeated the first query (the production trail shape)", () => {
    const prod = claim({
      queries: [q("vitamin newborn bleeding")],
      rounds: [round(1, "vitamin newborn bleeding"), round(2, "vitamin newborn bleeding", true), round(3, "vitamin newborn bleeding", true)],
      roundsUsed: 3,
      budgetExhausted: true,
    });
    const f = searchFinding(prod, false)!;
    expect(f).toBe("No study was found after 1 search, so this claim could not be checked. No other search terms were left to try.");
    expect(f).not.toMatch(/all 3 rounds/);
  });

  it("handles older runs that kept only the planned queries", () => {
    expect(searchFinding(claim({ queries: [q("a"), q("b")], partial: true, retrieved: null }), false)).toBe(
      "This claim was searched with 2 queries; this older analysis didn't record what each search returned.",
    );
  });

  it("never uses the critic's pipeline wording or internal codes", () => {
    const cases = [
      claim({ queries: [q("a")], rounds: [round(1, "a"), round(2, "a", true)], retrieved: 3, screened: 3, kept: 0, budgetExhausted: true }),
      claim({ queries: [q("a")], retrieved: 3, screened: 3, kept: 0 }, [], "UNSUPPORTED"),
      claim({ queries: [q("a")], kept: 1 }, [src("1", "CONSIDERED")]),
      claim({ queries: [q("a", true)] }),
    ];
    for (const c of cases) expect(searchFinding(c, true)).not.toMatch(/search again|budget|abstain|[A-Z]{2,}_[A-Z]|_/);
  });

  it("returns nothing without a search trail", () => {
    expect(searchFinding({ search: null, sources: [], verdict: null }, true)).toBeNull();
  });

  it("works on the stored trail: the repeated round isn't counted, and the flagged claim says so", () => {
    const r = adaptResult(MOCK_MISINFO_PENDING);
    const c3 = r.claims[2];
    expect(c3.search?.rounds).toHaveLength(3);
    expect(searchFinding(c3, flaggedClaimIds(r).has(c3.id))).toBe(
      "No relevant study was found after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so this claim could not be checked and was sent to a reviewer. No other search terms were left to try.",
    );
  });
});

describe("searchFinding: the claim's verdict (T52 review)", () => {
  const offTopic = { queries: [q("a"), q("b")], retrieved: 3, screened: 3, kept: 0 };
  const considered = { queries: [q("a")], retrieved: 5, screened: 4, kept: 2 };

  it.each([
    ["INSUFFICIENT_EVIDENCE", "No relevant study was found after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so this claim could not be checked and was sent to a reviewer."],
    ["UNSUPPORTED", "No study was found that tests this claim after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so the claim is treated as unproven and was sent to a reviewer."],
    ["NOT_VERIFIABLE", "No relevant study was found after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so this claim could not be checked and was sent to a reviewer."],
  ] as const)("papers retrieved, none relevant: %s", (verdict, text) => {
    expect(searchFinding(claim(offTopic, [], verdict), true)).toBe(text);
  });

  it.each([
    ["INSUFFICIENT_EVIDENCE", /none of them supported or contradicted the claim, so this claim could not be checked\.$/],
    ["UNSUPPORTED", /^No study was found that tests this claim after 1 search\. .* so the claim is treated as unproven\.$/],
  ] as const)("sources checked, none tested the claim: %s", (verdict, text) => {
    expect(searchFinding(claim(considered, [src("1", "CONSIDERED"), src("2", "CONSIDERED")], verdict), false)).toMatch(text);
  });

  it("an UNSUPPORTED claim with nothing found is unproven, not unchecked", () => {
    const f = searchFinding(claim({ queries: [q("a")] }, [], "UNSUPPORTED"), false);
    expect(f).toBe("No study was found after 1 search, so the claim is treated as unproven.");
    expect(f).not.toMatch(/could not be checked/);
  });

  it("verdicts backed by sources keep the sources' own wording", () => {
    const f = searchFinding(claim({ queries: [q("a")], kept: 1 }, [src("1", "CONTRADICTS")], "CONTRADICTED"), false);
    expect(f).toBe("1 source was checked against this claim after 1 search: 1 contradicts it.");
  });
});

describe("unusedSources", () => {
  it("lists only sources that neither supported nor contradicted the claim", () => {
    expect(unusedSources({ sources: [src("1", "CONSIDERED"), src("2", "SUPPORTS"), src("3", "CONTRADICTS")] }).map((s) => s.id)).toEqual(["1"]);
  });
});
