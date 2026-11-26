import { describe, expect, it } from "vitest";
import { decideAccess, hasRole, requiredRole, roleOf, safeNext } from "./roles";

const user = (role?: unknown) => ({ app_metadata: role === undefined ? {} : { role } });

describe("roleOf", () => {
  it("reads app_metadata.role", () => {
    expect(roleOf(user("reviewer"))).toBe("reviewer");
    expect(roleOf(user("admin"))).toBe("admin");
  });

  it("ignores user_metadata, which users can edit", () => {
    expect(roleOf({ app_metadata: {}, user_metadata: { role: "admin" } } as never)).toBe("analyst");
  });

  it("reads app_metadata.roles and takes the highest rank", () => {
    expect(roleOf({ app_metadata: { roles: ["analyst", "reviewer"] } })).toBe("reviewer");
    expect(roleOf({ app_metadata: { role: "reviewer", roles: ["admin"] } })).toBe("admin");
    expect(roleOf({ app_metadata: { role: "admin", roles: ["analyst"] } })).toBe("admin");
    expect(roleOf({ app_metadata: { roles: ["bogus", "reviewer"] } })).toBe("reviewer");
    expect(roleOf({ app_metadata: { roles: "admin" } })).toBe("analyst");
  });

  it("treats an unknown or missing role as analyst, like the backend", () => {
    expect(roleOf(user("superuser"))).toBe("analyst");
    expect(roleOf(user())).toBe("analyst");
  });

  it("has no role when signed out", () => {
    expect(roleOf(null)).toBeNull();
  });
});

describe("hasRole", () => {
  it("ranks analyst < reviewer < admin", () => {
    expect(hasRole("admin", "reviewer")).toBe(true);
    expect(hasRole("reviewer", "reviewer")).toBe(true);
    expect(hasRole("analyst", "reviewer")).toBe(false);
    expect(hasRole("reviewer", "admin")).toBe(false);
    expect(hasRole(null, "analyst")).toBe(false);
  });
});

describe("requiredRole", () => {
  it.each([
    ["/", "analyst"],
    ["/jobs/abc", "analyst"],
    ["/review", "reviewer"],
    ["/review/123", "reviewer"],
    ["/reviewers-guide", "analyst"],
    ["/evaluation", "admin"],
    ["/admin/evals", "admin"],
    ["/administrative-guide", "analyst"],
  ])("%s needs %s", (path, role) => {
    expect(requiredRole(path)).toBe(role);
  });
});

describe("decideAccess", () => {
  it("lets anyone open the sign-in page and the auth callback", () => {
    expect(decideAccess("/sign-in", "", null)).toEqual({ kind: "allow" });
    expect(decideAccess("/auth/callback", "?code=x", null)).toEqual({ kind: "allow" });
  });

  it("sends signed-out users to sign in, remembering where they were going", () => {
    expect(decideAccess("/jobs/abc", "?claim=c1", null)).toEqual({ kind: "sign-in", next: "/jobs/abc?claim=c1" });
  });

  it("denies a page above the user's role instead of redirecting", () => {
    expect(decideAccess("/review", "", user("analyst"))).toEqual({ kind: "denied", need: "reviewer" });
    expect(decideAccess("/evaluation", "", user("reviewer"))).toEqual({ kind: "denied", need: "admin" });
  });

  it("keeps /admin/evals (T63) to admins: analysts and reviewers are denied, signed-out users sign in", () => {
    expect(decideAccess("/admin/evals", "", user("analyst"))).toEqual({ kind: "denied", need: "admin" });
    expect(decideAccess("/admin/evals", "", user("reviewer"))).toEqual({ kind: "denied", need: "admin" });
    expect(decideAccess("/admin/evals", "", user())).toEqual({ kind: "denied", need: "admin" });
    expect(decideAccess("/admin/evals", "", user("admin"))).toEqual({ kind: "allow" });
    expect(decideAccess("/admin/evals", "", null)).toEqual({ kind: "sign-in", next: "/admin/evals" });
  });

  it("allows a page at or below the user's role", () => {
    expect(decideAccess("/review/1", "", user("reviewer"))).toEqual({ kind: "allow" });
    expect(decideAccess("/evaluation", "", user("admin"))).toEqual({ kind: "allow" });
    expect(decideAccess("/", "", user())).toEqual({ kind: "allow" });
  });
});

describe("safeNext", () => {
  it.each([
    ["/jobs/abc?claim=c1", "/jobs/abc?claim=c1"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["javascript:alert(1)", "/"],
    ["/sign-in", "/"],
    ["/ok\nLocation: x", "/"],
    [null, "/"],
    ["", "/"],
  ])("%s → %s", (input, out) => {
    expect(safeNext(input as string | null)).toBe(out);
  });
});

describe("/dashboard (T62)", () => {
  it("is open to every signed-in role and sends signed-out users to sign in", () => {
    for (const r of ["analyst", "reviewer", "admin", undefined]) expect(decideAccess("/dashboard", "", user(r))).toEqual({ kind: "allow" });
    expect(decideAccess("/dashboard", "", null)).toEqual({ kind: "sign-in", next: "/dashboard" });
  });
});
