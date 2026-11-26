import { describe, expect, it } from "vitest";
import { initials, navFor, NAV } from "./nav";

describe("navFor", () => {
  it("shows nothing when signed out", () => expect(navFor(null)).toEqual([]));
  it("shows analyst items to every role", () => {
    for (const r of ["analyst", "reviewer", "admin"] as const) expect(navFor(r).length).toBeGreaterThan(0);
  });
  it("never shows an item above the user's role", () => {
    const reviewerOnly = NAV.filter((i) => i.role !== "analyst").map((i) => i.href);
    expect(navFor("analyst").map((i) => i.href)).not.toEqual(expect.arrayContaining(reviewerOnly.length ? reviewerOnly : ["/__none__"]));
  });
});

describe("initials", () => {
  it.each([
    ["a.mensah@who-research.org", "AM"],
    ["prc4@illinois.example", "PR"],
    ["", "?"],
    [null, "?"],
  ])("%s → %s", (email, out) => expect(initials(email)).toBe(out));
});

describe("dashboard nav (T62)", () => {
  it("lists the Dashboard for every signed-in role", () => {
    for (const r of ["analyst", "reviewer", "admin"] as const) expect(navFor(r).map((i) => i.href)).toContain("/dashboard");
  });
});
