import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { decisionRequest, preRevealRequest } from "@/lib/review/decision";
import { MOCK_VIEWER_ID, mockRevealed } from "./mocks/reviews";
import { fetchCaseEvidence, postDecision, postPreReveal } from "./reviews";
import { MOCK_MISINFO_PENDING } from "./mocks/results";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const req = decisionRequest({ kind: "APPROVE", correctedLabel: null, reasonCode: "SYSTEM_CORRECT", note: "Both sources contradict it.", claimCorrections: [] });

beforeEach(() => apiFetch.mockReset());

describe("postDecision (T34)", () => {
  it("posts the reason code next to the note", async () => {
    apiFetch.mockResolvedValue(json(200, {}));
    expect(await postDecision("rev-1", req)).toEqual({ ok: true });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe("/v1/reviews/rev-1/decision");
    expect(JSON.parse(init.body)).toMatchObject({ reason: "Both sources contradict it.", reason_code: "SYSTEM_CORRECT" });
  });

  it("tells the reviewer to record their judgement first on PRE_REVEAL_REQUIRED", async () => {
    apiFetch.mockResolvedValue(json(409, { detail: { code: "PRE_REVEAL_REQUIRED", message: "…" } }));
    const r = await postDecision("rev-1", req);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(/Record your own judgement/);
  });

  it("keeps the 'someone else decided' message for other conflicts", async () => {
    apiFetch.mockResolvedValue(json(409, { detail: "review is already resolved" }));
    const r = await postDecision("rev-1", req);
    if (!r.ok) expect(r.message).toMatch(/Someone else decided/);
  });
});

describe("postPreReveal (T34)", () => {
  const body = preRevealRequest([{ claimId: "c1", stance: "REFUTES", verdict: "CONTRADICTED" }]);

  it("posts the judgement and reads the revealed case the server answers with", async () => {
    apiFetch.mockResolvedValue(json(201, mockRevealed(body.claims)));
    const r = await postPreReveal("rev-1", body, MOCK_VIEWER_ID);
    expect(apiFetch.mock.calls[0][0]).toBe("/v1/reviews/rev-1/pre-reveal");
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual(body);
    expect(r.ok && r.data.withheld).toBe(false);
    expect(r.ok && r.data.myPreReveal).toEqual([{ claimId: "c1", stance: "REFUTES", verdict: "CONTRADICTED" }]);
  });

  it.each([
    [409, /already recorded/],
    [403, /videos you submitted/],
    [422, /every claim/],
  ])("explains a %i in plain words", async (status, msg) => {
    apiFetch.mockResolvedValue(json(status, { detail: "x" }));
    const r = await postPreReveal("rev-1", body);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(msg);
  });
});

describe("fetchCaseEvidence (T34 blind step)", () => {
  it("reads the result once revealed", async () => {
    apiFetch.mockResolvedValue(json(200, MOCK_MISINFO_PENDING));
    const ev = await fetchCaseEvidence("job 1");
    expect(apiFetch.mock.calls[0][0]).toBe("/jobs/job%201/result");
    expect(ev.kind).toBe("ok");
  });

  it("treats 403 PRE_REVEAL_REQUIRED as 'still blind', not an error", async () => {
    apiFetch.mockResolvedValue(json(403, { detail: { code: "PRE_REVEAL_REQUIRED", message: "…" } }));
    expect(await fetchCaseEvidence("j")).toEqual({ kind: "blind" });
  });

  it("reports another 403 as an error", async () => {
    apiFetch.mockResolvedValue(json(403, { detail: "Not allowed" }));
    expect(await fetchCaseEvidence("j")).toEqual({ kind: "error" });
  });

  it("reports a lost connection as an error", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("offline"));
    expect(await fetchCaseEvidence("j")).toEqual({ kind: "error" });
  });
});
