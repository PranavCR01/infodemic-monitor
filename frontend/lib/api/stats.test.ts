import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { fetchStats } from "./stats";
import { adaptStats, cellText, formatHours, formatShare, scaleMax, toCell } from "./stats-adapter";
import { MOCK_STATS_30D, MOCK_STATS_ALL } from "./mocks/stats";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
beforeEach(() => apiFetch.mockReset());

describe("toCell (T62 small cells)", () => {
  it("keeps '<5' suppressed and never turns it into a number", () => {
    expect(toCell("<5")).toEqual({ suppressed: true });
    expect(cellText(toCell("<5"))).toBe("<5");
  });

  it.each([0, 1, 4, -3, NaN, null, undefined])("suppresses %s rather than showing it", (v) => {
    expect(toCell(v as never)).toEqual({ suppressed: true });
  });

  it("publishes counts of 5 or more", () => {
    expect(toCell(5)).toEqual({ suppressed: false, n: 5 });
    expect(cellText(toCell(1234))).toBe("1,234");
  });
});

describe("adaptStats", () => {
  const m = adaptStats(MOCK_STATS_30D);

  it("keeps the labels in a fixed order with display names", () => {
    expect(m.labels.map((l) => [l.label, cellText(l.cell)])).toEqual([
      ["MISINFO", "12"],
      ["NO-MISINFO", "7"],
      ["DEBUNKED", "5"],
      ["CANNOT RECOGNIZE", "6"],
    ]);
  });

  it("splits MISINFO by basis, suppressed cells kept as suppressed", () => {
    expect(m.misinfoBasis.map((b) => cellText(b.cell))).toEqual(["6", "<5", "<5", "<5"]);
  });

  it("leaves suppressed cells out of a chart's scale", () => {
    expect(scaleMax(m.perWeek)).toBe(19);
    expect(scaleMax(m.misinfoBasis)).toBe(6);
  });

  it("keeps null share and median as null", () => {
    expect(m.reviews.changedShare).toBeNull();
    expect(m.reviews.medianHours).toBe(4.5);
  });

  it("names claim categories in plain words, unknown ones readably", () => {
    expect(adaptStats(MOCK_STATS_ALL).categories.map((c) => c.label)).toEqual(["Treatment works", "About the evidence itself", "Some new category"]);
  });

  it("drops a category under 5 if one slips through", () => {
    const raw = { ...MOCK_STATS_30D, top_categories: [{ category: "safety", videos: "<5" as const }, { category: "prevention", videos: 7 }] };
    expect(adaptStats(raw).categories.map((c) => c.key)).toEqual(["prevention"]);
  });

  it("carries no id of any video, job or user", () => {
    expect(JSON.stringify(adaptStats(MOCK_STATS_ALL))).not.toMatch(/video_id|job_id|user_id|submitted_by|filename/);
  });
});

describe("display", () => {
  it("formats the share and median, null stays null", () => {
    expect(formatShare(0.25)).toBe("25%");
    expect(formatShare(null)).toBeNull();
    expect(formatHours(4.5)).toBe("4.5 hours");
    expect(formatHours(0.25)).toBe("15 minutes");
    expect(formatHours(72)).toBe("3.0 days");
    expect(formatHours(null)).toBeNull();
  });
});

describe("fetchStats", () => {
  it("asks for the chosen window", async () => {
    apiFetch.mockResolvedValueOnce(json(200, MOCK_STATS_ALL));
    expect((await fetchStats("all")).kind).toBe("ok");
    expect(apiFetch).toHaveBeenCalledWith("/v1/stats?window=all");
  });

  it.each([
    [401, "sign-in"],
    [500, "error"],
    [422, "error"],
  ])("maps %s to %s", async (status, kind) => {
    apiFetch.mockResolvedValueOnce(json(status, {}));
    expect((await fetchStats("30d")).kind).toBe(kind);
  });

  it("reports a lost connection", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect(await fetchStats("30d")).toEqual({ kind: "error", message: expect.stringMatching(/no connection/) });
  });
});
