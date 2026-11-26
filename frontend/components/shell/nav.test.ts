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

describe("admin nav (T63)", () => {
  it("lists Evaluations for admins only", () => {
    expect(navFor("admin").map((i) => i.href)).toContain("/admin/evals");
    expect(navFor("reviewer").map((i) => i.href)).not.toContain("/admin/evals");
    expect(navFor("analyst").map((i) => i.href)).not.toContain("/admin/evals");
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
