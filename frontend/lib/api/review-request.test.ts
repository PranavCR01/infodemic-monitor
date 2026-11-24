import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { requestNoteProblem, requestReview } from "./review-request";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
beforeEach(() => apiFetch.mockReset());

describe("requestReview (T32)", () => {
  it("posts only the trimmed note (T32 forbids other fields)", async () => {
    apiFetch.mockResolvedValueOnce(json(201, { created: true, review_id: "r1" }));
    expect(await requestReview("j1", "  claim 2 looks misread  ")).toEqual({ ok: true, created: true });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe("/v1/jobs/j1/review-request");
    expect(JSON.parse(init.body)).toEqual({ note: "claim 2 looks misread" });
  });

  it("treats an existing case (200) as success", async () => {
    apiFetch.mockResolvedValueOnce(json(200, { created: false }));
    expect(await requestReview("j1", "x")).toEqual({ ok: true, created: false });
  });

  it("explains 409 and failures in plain words", async () => {
    apiFetch.mockResolvedValueOnce(json(409, { detail: "job not finished" }));
    expect(await requestReview("j1", "x")).toEqual({ ok: false, message: expect.stringMatching(/once the analysis has finished/) });
    apiFetch.mockRejectedValueOnce(new TypeError("offline"));
    expect(await requestReview("j1", "x")).toEqual({ ok: false, message: expect.stringMatching(/no connection/) });
  });
});

describe("requestNoteProblem", () => {
  it("requires a note, within T32's limit", () => {
    expect(requestNoteProblem("   ")).toMatch(/Say what looks wrong/);
    expect(requestNoteProblem("x".repeat(2001))).toMatch(/under 2000/);
    expect(requestNoteProblem("Check claim 2")).toBeNull();
  });
});
