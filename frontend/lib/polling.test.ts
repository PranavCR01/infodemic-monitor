import { describe, expect, it } from "vitest";
import { isLost, nextDelay } from "./polling";

describe("nextDelay", () => {
  it("polls every 3 s for the first 3 minutes, then every 10 s", () => {
    expect(nextDelay({ elapsedMs: 0, failures: 0, done: false })).toBe(3000);
    expect(nextDelay({ elapsedMs: 179_999, failures: 0, done: false })).toBe(3000);
    expect(nextDelay({ elapsedMs: 180_000, failures: 0, done: false })).toBe(10000);
  });

  it("stops when the job is done", () => {
    expect(nextDelay({ elapsedMs: 0, failures: 5, done: true })).toBeNull();
  });

  it("keeps the normal pace for one or two failures", () => {
    expect(nextDelay({ elapsedMs: 0, failures: 2, done: false })).toBe(3000);
    expect(isLost(2)).toBe(false);
  });

  it("backs off 3 → 10 → 20 s after 3 failures in a row, and stays at 20 s", () => {
    expect(isLost(3)).toBe(true);
    expect([3, 4, 5, 9].map((failures) => nextDelay({ elapsedMs: 0, failures, done: false }))).toEqual([3000, 10000, 20000, 20000]);
  });

  it("accepts a different base pace (jobs list: 10 s)", () => {
    expect(nextDelay({ elapsedMs: 0, failures: 0, done: false }, { fastMs: 10_000 })).toBe(10_000);
  });
});
