import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { rateLimitMessage, requestReanalysis, retryText } from "./reanalyse";

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
beforeEach(() => apiFetch.mockReset());

describe("retryText", () => {
  it.each([
    [30, "in a minute"],
    [61, "in about 2 minutes"],
    [59 * 60, "in about 59 minutes"],
    [60 * 60, "in about an hour"],
    [3 * 3600 + 1, "in about 4 hours"],
  ])("%i s → %s (rounded up, never sooner)", (s, text) => {
    expect(retryText(s)).toBe(text);
  });
});

describe("rateLimitMessage (T55 429)", () => {
  it("names the per-video limit and when to try again, preferring the Retry-After header", () => {
    const m = rateLimitMessage({ limit_kind: "per_video", limit: 3, window_hours: 24, retry_after_seconds: 60 }, "7200");
    expect(m).toBe("This video has already been re-analysed 3 times in the last 24 hours. You can re-analyse it again in about 2 hours.");
  });

  it("names the per-user limit", () => {
    expect(rateLimitMessage({ limit_kind: "per_user", limit: 20, window_hours: 24, retry_after_seconds: 1800 }, null)).toBe(
      "You've used all 20 re-analyses allowed in 24 hours. You can start another one in about 30 minutes.",
    );
  });
});

describe("requestReanalysis (T55)", () => {
  it("posts only the trimmed reason, or an empty body, and returns the new job", async () => {
    apiFetch.mockResolvedValue(json(202, { job_id: "new-job", reanalyses_remaining: 2 }));
    expect(await requestReanalysis("vid 1", "  pipeline v2  ")).toEqual({ ok: true, jobId: "new-job", remaining: 2 });
    expect(apiFetch.mock.calls[0][0]).toBe("/v1/videos/vid%201/reanalyse");
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ reason: "pipeline v2" });
    await requestReanalysis("v", "   ");
    expect(JSON.parse(apiFetch.mock.calls[1][1].body)).toEqual({});
  });

  it("explains a 429 with the limit and Retry-After", async () => {
    apiFetch.mockResolvedValue(
      json(429, { detail: { code: "REANALYSIS_RATE_LIMITED", limit_kind: "per_video", limit: 3, window_hours: 24, retry_after_seconds: 5000 } }, { "Retry-After": "5000" }),
    );
    const r = await requestReanalysis("v", "");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(/re-analysed 3 times in the last 24 hours\. You can re-analyse it again in about 2 hours\./);
  });

  it.each([
    [403, { detail: { code: "REANALYSIS_FORBIDDEN" } }, /Only the person who submitted this video, or an admin/],
    [403, { detail: { code: "REANALYSIS_DISABLED" } }, /turned off/],
    [404, { detail: "Video not found" }, /can't find this video/],
    [500, {}, /couldn't be started/],
  ])("explains a %i in plain words", async (status, body, msg) => {
    apiFetch.mockResolvedValue(json(status, body));
    const r = await requestReanalysis("v", "");
    if (!r.ok) expect(r.message).toMatch(msg);
    else throw new Error("expected a failure");
  });

  it("refuses an over-long reason without calling the API", async () => {
    const r = await requestReanalysis("v", "x".repeat(2001));
    expect(r.ok).toBe(false);
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
