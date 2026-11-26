import { describe, expect, it } from "vitest";
import {
  claimMeaning,
  displayText,
  JOB_STATES,
  LABELS,
  labelDisplay,
  reasonRule,
  reasonText,
  REVIEW_REASONS,
  REVIEW_STATUS,
  SEVERITY,
  STANCE_VALUES,
  STANCES,
  toJobState,
  VERDICT_VALUES,
  VERDICTS,
  VIDEO_LABELS,
} from "./vocabulary";

const INTERNAL = /[A-Z]+_[A-Z_]+/; // NO_MISINFO, INSUFFICIENT_EVIDENCE, ...

describe("display names never leak internal enums", () => {
  const all = [
    ...Object.values(LABELS),
    ...Object.values(VERDICTS),
    ...Object.values(STANCES),
    ...Object.values(REVIEW_STATUS),
    ...Object.values(JOB_STATES),
    ...Object.values(SEVERITY),
  ];
  it.each(all.map((m) => [m.display]))("%s", (display) => {
    expect(display).not.toMatch(INTERNAL);
  });

  it("uses the brief's names for the four labels", () => {
    expect(VIDEO_LABELS.map((l) => LABELS[l].display)).toEqual([
      "MISINFO",
      "NO-MISINFO",
      "DEBUNKED",
      "CANNOT RECOGNIZE",
    ]);
  });
});

describe("the four labels can't be told apart by colour alone", () => {
  it("each has its own icon and its own tone", () => {
    const icons = VIDEO_LABELS.map((l) => LABELS[l].icon);
    const tones = VIDEO_LABELS.map((l) => LABELS[l].tone);
    expect(new Set(icons).size).toBe(4);
    expect(new Set(tones).size).toBe(4);
  });

  it("DEBUNKED never shares MISINFO's tone or icon", () => {
    expect(LABELS.DEBUNKING.tone).not.toBe(LABELS.MISINFO.tone);
    expect(LABELS.DEBUNKING.icon).not.toBe(LABELS.MISINFO.icon);
  });

  it("CANNOT RECOGNIZE is an abstention, not an error", () => {
    expect(LABELS.CANNOT_RECOGNIZE.tone).toBe("abstain");
    expect(LABELS.CANNOT_RECOGNIZE.icon).not.toBe("alert");
    expect(LABELS.CANNOT_RECOGNIZE.dashed).toBe(true);
  });
});

describe("verdicts", () => {
  it("INSUFFICIENT EVIDENCE never looks like CONTRADICTED", () => {
    const ins = VERDICTS.INSUFFICIENT_EVIDENCE;
    const con = VERDICTS.CONTRADICTED;
    expect(ins.tone).not.toBe(con.tone);
    expect(ins.icon).not.toBe(con.icon);
    expect(ins.dashed).toBe(true);
    expect(ins.description).toMatch(/not the same as false/);
  });

  it("UNSUPPORTED (D1 = B) is distinct from both CONTRADICTED and INSUFFICIENT EVIDENCE", () => {
    const u = VERDICTS.UNSUPPORTED;
    expect(u.tone).toBe("unsupported");
    expect(u.icon).not.toBe(VERDICTS.CONTRADICTED.icon);
    expect(u.display).not.toBe(VERDICTS.INSUFFICIENT_EVIDENCE.display);
    expect(u.description).toMatch(/Not proven false/);
    expect(u.display.toLowerCase()).not.toContain("false");
  });

  it("every verdict has a distinct display name", () => {
    expect(new Set(VERDICT_VALUES.map((v) => VERDICTS[v].display)).size).toBe(VERDICT_VALUES.length);
  });
});

describe("stance chips carry no colour", () => {
  it.each(STANCE_VALUES)("%s has no tone", (s) => {
    expect("tone" in STANCES[s]).toBe(false);
  });
});

describe("labelDisplay", () => {
  it("shows MISINFO (unproven) for the unproven basis only", () => {
    expect(labelDisplay("MISINFO", "unproven").display).toBe("MISINFO (unproven)");
    expect(labelDisplay("MISINFO", "contradicted").display).toBe("MISINFO");
    expect(labelDisplay("MISINFO", "denies_supported").display).toBe("MISINFO");
    expect(labelDisplay("MISINFO").display).toBe("MISINFO");
  });

  it("ignores a basis on other labels", () => {
    expect(labelDisplay("DEBUNKING", "unproven").display).toBe("DEBUNKED");
  });
});

describe("claimMeaning", () => {
  it("names a debunk as a correction", () => {
    expect(claimMeaning("REFUTES", "CONTRADICTED")).toBe(
      "The speaker refutes a claim the evidence contradicts. This corrects misinformation.",
    );
  });

  it("names promoting a false claim", () => {
    expect(claimMeaning("ENDORSES", "CONTRADICTED")).toBe("The speaker promotes a claim that the evidence contradicts.");
  });

  it("never calls an unproven claim false", () => {
    const s = claimMeaning("ENDORSES", "UNSUPPORTED");
    expect(s).toBe("The speaker presents an untested remedy as working. No evidence supports it.");
    expect(s.toLowerCase()).not.toContain("false");
  });

  it("treats every unsettled verdict alike", () => {
    for (const v of ["MIXED", "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"] as const) {
      expect(claimMeaning("ENDORSES", v)).toBe("The speaker promotes a claim no study settles.");
    }
  });

  it("says the position is unclear for NEUTRAL and UNCLEAR, whatever the verdict", () => {
    for (const v of VERDICT_VALUES) {
      expect(claimMeaning("NEUTRAL", v)).toMatch(/not clear/);
      expect(claimMeaning("UNCLEAR", v)).toMatch(/not clear/);
    }
  });

  it("has a sentence for every stance × verdict", () => {
    for (const s of STANCE_VALUES) for (const v of VERDICT_VALUES) expect(claimMeaning(s, v)).toMatch(/\.$/);
  });
});

describe("toJobState", () => {
  it.each([
    ["PENDING", "QUEUED"],
    ["QUEUED", "QUEUED"],
    ["STARTED", "RUNNING"],
    ["RUNNING", "RUNNING"],
    ["RETRY_PENDING", "RETRYING"],
    ["REVIEW_REQUIRED", "NEEDS_REVIEW"],
    ["SUCCESS", "COMPLETED"],
    ["COMPLETED", "COMPLETED"],
    ["REJECTED", "COMPLETED"],
    ["FAILED", "FAILED"],
  ])("%s → %s", (raw, state) => {
    expect(toJobState(raw)).toBe(state);
  });

  it("returns null for unknown values instead of passing them through", () => {
    expect(toJobState("SOMETHING_NEW")).toBeNull();
    expect(toJobState(null)).toBeNull();
  });
});

describe("review reasons", () => {
  it("finds the rule in stored codes", () => {
    expect(reasonRule("weak_evidence:c1")).toBe("weak_evidence");
    expect(reasonRule("judge:possible_debunk:c2")).toBe("possible_debunk");
    expect(reasonRule("low_confidence")).toBe("low_confidence");
    expect(reasonRule("validation_failed:not_run")).toBe("validation_failed");
  });

  it("gives plain language, never the code", () => {
    expect(reasonText("unproven_claim:c3")).toBe(REVIEW_REASONS.unproven_claim);
    // T37: a video-level reason with no claim id
    expect(reasonRule("nothing_judged")).toBe("nothing_judged");
    expect(reasonText("nothing_judged")).toBe("No claim in this video could be checked against the evidence.");
    // T67: the critic is "a second automated check" in user-facing text (T65)
    expect(reasonText("second_check_disagreed:c4")).toBe(REVIEW_REASONS.second_check_disagreed);
    expect(reasonText("second_check_disagreed:c4")).toContain("second automated check");
    expect(reasonText("second_check_disagreed:c4")).not.toMatch(/critic/i);
    expect(reasonRule("judge:thin_contradiction:c2")).toBe("thin_contradiction");
    expect(reasonText("judge:thin_contradiction:c2")).toBe(REVIEW_REASONS.thin_contradiction);
    const unknown = reasonText("brand_new_rule:c9");
    expect(unknown).not.toContain("brand_new_rule");
    expect(unknown).not.toContain("c9");
  });

  it("every reason sentence is free of internal names", () => {
    for (const s of Object.values(REVIEW_REASONS)) expect(s).not.toMatch(INTERNAL);
  });
});

describe("displayText", () => {
  it("replaces internal enums in backend text", () => {
    expect(displayText("CANNOT_RECOGNIZE: no checkable health claims were found in the video.")).toBe(
      "CANNOT RECOGNIZE: no checkable health claims were found in the video.",
    );
    expect(displayText("claim c1 insufficient: INSUFFICIENT_EVIDENCE")).toBe("claim c1 insufficient: insufficient evidence");
  });

  it("leaves ordinary text alone", () => {
    expect(displayText("MISINFO: claim one is contradicted.")).toBe("MISINFO: claim one is contradicted.");
    expect(displayText(null)).toBe("");
  });
});
