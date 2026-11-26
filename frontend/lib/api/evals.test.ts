import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { fetchEvals } from "./evals";
import {
  adaptEvals,
  filterEvals,
  formatCost,
  formatValue,
  groupByStep,
  NO_FILTERS,
  sortEvals,
  stepOptions,
  taskOptions,
} from "./evals-adapter";
import { MOCK_EVALS } from "./mocks/evals";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
beforeEach(() => apiFetch.mockReset());

describe("adaptEvals (T63)", () => {
  const { runs, total } = adaptEvals(MOCK_EVALS);
  const byId = (id: string) => runs.find((r) => r.runId === id)!;

  it("keeps every record and the API's total", () => {
    expect(total).toBe(6);
    expect(runs).toHaveLength(6);
  });

  it("reads a null split as 'not a golden split', and keeps the synthetic flag", () => {
    expect(byId("T05-rerank-precision_at_5-reranked")).toMatchObject({ split: "none", synthetic: true, models: [] });
    expect(byId("T43-extraction_ceiling-claim_f1_strict")).toMatchObject({ split: "tune", synthetic: false, models: null });
  });

  it("keeps the CI only when the record has one", () => {
    expect(byId("T43-extraction_ceiling-claim_f1_strict").ci).toEqual({ low: 0.586, high: 0.761, method: "bootstrap over videos, 1000 resamples" });
    expect(byId("T38-verify_claims-claude-opus-5-5").ci).toBeNull();
  });

  it("counts the records that share a run group (cost is per group)", () => {
    expect(byId("FIXTURE-verify-test-recall").groupSize).toBe(2);
    expect(byId("T38-verify_claims-claude-opus-5-5").groupSize).toBe(1);
  });

  it("drops a report link that isn't http(s)", () => {
    expect(byId("FIXTURE-verify-test-recall").reportUrl).toBeNull();
    expect(byId("T38-verify_claims-claude-opus-5-5").reportUrl).toMatch(/^https:\/\/github\.com\//);
  });

  it("gives steps plain names", () => {
    expect(byId("T38-verify_claims-claude-opus-5-5").stepLabel).toBe("Check claims against evidence");
  });
});

describe("filters and order", () => {
  const { runs } = adaptEvals(MOCK_EVALS);

  it("orders by pipeline step, newest first within a step", () => {
    expect(sortEvals(runs, "step").map((r) => r.runId)).toEqual([
      "T43-extraction_ceiling-claim_f1_strict",
      "T05-rerank-precision_at_5-reranked",
      "FIXTURE-verify-test-precision",
      "FIXTURE-verify-test-recall",
      "T38-verify_claims-claude-opus-5-5",
      "T24-judge_crosscheck-label_agreement",
    ]);
    expect(groupByStep(sortEvals(runs, "step")).map((g) => [g.step, g.runs.length])).toEqual([
      ["extract_claims", 1],
      ["rerank_evidence", 1],
      ["verify_claims", 3],
      ["judge_classification", 1],
    ]);
  });

  it("orders by date alone, newest first", () => {
    expect(sortEvals(runs, "newest").map((r) => r.date)).toEqual(["2026-11-26", "2026-11-26", "2026-11-24", "2026-11-24", "2026-11-23", "2026-11-22"]);
  });

  it("filters by task, step and split, and combines them", () => {
    expect(filterEvals(runs, NO_FILTERS)).toHaveLength(6);
    expect(filterEvals(runs, { ...NO_FILTERS, task: "T38" }).map((r) => r.runId)).toEqual(["T38-verify_claims-claude-opus-5-5"]);
    expect(filterEvals(runs, { ...NO_FILTERS, step: "verify_claims" })).toHaveLength(3);
    expect(filterEvals(runs, { ...NO_FILTERS, split: "none" }).map((r) => r.task).sort()).toEqual(["T05", "T24"]);
    expect(filterEvals(runs, { task: null, step: "verify_claims", split: "tune" }).map((r) => r.task)).toEqual(["T38"]);
  });

  it("offers tasks in number order and steps in pipeline order", () => {
    expect(taskOptions(runs)).toEqual(["T05", "T24", "T38", "T43", "T60"]);
    expect(stepOptions(runs).map((s) => s.step)).toEqual(["extract_claims", "rerank_evidence", "verify_claims", "judge_classification"]);
  });
});

describe("display", () => {
  it.each([
    [0.6759, "0.6759"],
    [0.68, "0.68"],
    [1, "1"],
    [0.123456, "0.1235"],
    [null, "Not computed"],
  ])("value %s → %s", (v, out) => expect(formatValue(v)).toBe(out));

  it.each([
    [0, "$0 (no paid calls)"],
    [5.9869, "$5.99"],
    [null, "Not recorded"],
  ])("cost %s → %s", (v, out) => expect(formatCost(v)).toBe(out));
});

describe("fetchEvals", () => {
  it("adapts a 200", async () => {
    apiFetch.mockResolvedValueOnce(json(200, MOCK_EVALS));
    const r = await fetchEvals();
    expect(r.kind).toBe("ok");
    expect(apiFetch).toHaveBeenCalledWith("/v1/admin/evals");
  });

  it.each([
    [401, "sign-in"],
    [403, "forbidden"],
    [500, "error"],
  ])("maps %s to %s", async (status, kind) => {
    apiFetch.mockResolvedValueOnce(json(status, { detail: "x" }));
    expect((await fetchEvals()).kind).toBe(kind);
  });

  it("reports a lost connection", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect(await fetchEvals()).toEqual({ kind: "error", message: expect.stringMatching(/no connection/) });
  });
});
