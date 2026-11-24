import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS } from "@/lib/job-filters";
import { filtersFromSearch, jobsQuery, searchFromFilters } from "./jobs";

describe("job filters and the URL", () => {
  it("round-trips through the URL", () => {
    const f = { q: "flu", state: "RETRYING" as const, label: "MISINFO", needsReview: false, page: 3 };
    expect(filtersFromSearch(new URLSearchParams(searchFromFilters(f)))).toEqual(f);
    expect(searchFromFilters(EMPTY_FILTERS)).toBe("");
  });

  it("ignores junk in the URL", () => {
    expect(filtersFromSearch(new URLSearchParams("state=EVIL&page=-2"))).toEqual(EMPTY_FILTERS);
  });

  it("builds T28's query: paging, search, label and state", () => {
    const q = new URLSearchParams(jobsQuery({ q: "flu", state: "COMPLETED", label: "DEBUNKING", needsReview: false, page: 2 }));
    expect(Object.fromEntries(q)).toEqual({ limit: "20", offset: "20", q: "flu", label: "DEBUNKING", status: "COMPLETED,REJECTED" });
  });

  it("maps 'Needs review only' to REVIEW_REQUIRED, over any state", () => {
    expect(new URLSearchParams(jobsQuery({ ...EMPTY_FILTERS, state: "FAILED", needsReview: true })).get("status")).toBe("REVIEW_REQUIRED");
  });
});
