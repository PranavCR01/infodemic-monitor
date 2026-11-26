import { describe, expect, it } from "vitest";
import { cleanClaimText, cleanTitle, formatPubDate, replaceEvidenceIds, secondCheckWording, shortSourceName } from "./report-text";

const SOURCES = [
  { id: "ev_k1", title: "Late bleeding in an infant: a case report.", pmid: "101" },
  { id: "ev_k2", title: "", pmid: "102" },
  { id: "ev_long", title: "A very long title about vitamin K prophylaxis in newborns across several countries and decades.", pmid: null },
];

describe("cleanTitle (T65 d)", () => {
  it.each([
    ["A narrative review.", "A narrative review"],
    ["A narrative review..", "A narrative review"],
    ["A narrative review. ", "A narrative review"],
    ["No full stop", "No full stop"],
    [null, ""],
  ])("%s → %s", (t, out) => expect(cleanTitle(t)).toBe(out));

  it("leaves one full stop when the title is printed with one", () => {
    expect(`${cleanTitle("A narrative review.")}. 2016`).toBe("A narrative review. 2016");
  });
});

describe("formatPubDate (T65 f)", () => {
  it.each([
    ["2026-11-05", "5 Nov 2026"],
    ["2026-11", "Nov 2026"],
    ["2026", "2026"],
    ["2026-13", "2026"],
    ["Nov 2026", null],
    ["", null],
    [null, null],
    [undefined, null],
  ])("%s → %s", (d, out) => expect(formatPubDate(d)).toBe(out));
});

describe("replaceEvidenceIds (T65 a)", () => {
  it("names a source by its short title", () => {
    expect(replaceEvidenceIds("As ev_k1 shows.", SOURCES)).toBe("As “Late bleeding in an infant: a case report” shows.");
  });

  it("uses the PMID when there is no title, and drops brackets around the name", () => {
    expect(replaceEvidenceIds("Weak [ev_k2].", SOURCES)).toBe("Weak PMID 102.");
  });

  it("shortens a long title at a word", () => {
    expect(shortSourceName(SOURCES[2])).toMatch(/^“A very long title about vitamin K prophylaxis in newborns…”$/);
  });

  it("never leaves an unknown id in the text", () => {
    expect(replaceEvidenceIds("See ev_zz9 and ev_k1.", SOURCES)).not.toMatch(/ev_/);
    expect(replaceEvidenceIds("See ev_zz9.", SOURCES)).toBe("See one of the sources.");
  });

  it("leaves text without ids alone", () => {
    expect(replaceEvidenceIds("Every level of evidence.", SOURCES)).toBe("Every level of evidence.");
  });
});

describe("secondCheckWording (T65 b)", () => {
  it.each([
    ["The reviewer noted the review is old.", "A second automated check noted the review is old."],
    ["Flagged by the reviewer.", "Flagged by a second automated check."],
    ["The reviewer's note: none.", "The second automated check's note: none."],
  ])("%s", (t, out) => expect(secondCheckWording(t)).toBe(out));

  it("doesn't touch other words", () => {
    expect(secondCheckWording("A systematic review of reviewers.")).toBe("A systematic review of reviewers.");
  });

  it("both fixes together", () => {
    expect(cleanClaimText("The reviewer cites ev_k1.", SOURCES)).toBe("A second automated check cites “Late bleeding in an infant: a case report”.");
  });
});
