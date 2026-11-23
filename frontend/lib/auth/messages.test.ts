import { describe, expect, it } from "vitest";
import { emailProblem, magicLinkOutcome, passwordSignInError } from "./messages";

describe("emailProblem", () => {
  it("asks for an email", () => expect(emailProblem("  ")).toMatch(/Enter your email/));
  it("rejects malformed addresses", () => expect(emailProblem("a.mensah")).toMatch(/like name@/));
  it("accepts a normal address", () => expect(emailProblem("a.mensah@who-research.org")).toBeNull());
});

describe("passwordSignInError", () => {
  it("never shows Supabase's own wording", () => {
    const s = passwordSignInError({ status: 400, message: "Invalid login credentials" });
    expect(s).not.toMatch(/credentials/i);
    expect(s).toMatch(/don't match/);
  });
  it("reports rate limits", () => expect(passwordSignInError({ status: 429 })).toMatch(/Too many/));
  it("explains unconfirmed addresses", () =>
    expect(passwordSignInError({ code: "email_not_confirmed", status: 400 })).toMatch(/invitation/));
  it("falls back to a generic message", () => expect(passwordSignInError({ status: 503 })).toMatch(/Try again/));
});

describe("magicLinkOutcome", () => {
  it("looks the same for unknown addresses as for known ones", () => {
    expect(magicLinkOutcome({ status: 422, message: "Signups not allowed for otp" })).toEqual({ sent: true });
    expect(magicLinkOutcome(null)).toEqual({ sent: true });
  });
  it("reports rate limits and outages", () => {
    expect(magicLinkOutcome({ status: 429 }).sent).toBe(false);
    expect(magicLinkOutcome({ status: 500 }).sent).toBe(false);
  });
});
