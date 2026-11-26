// GET /v1/stats fixtures (T62, shape from context/MULTI_AGENT.md §7ah).
import type { RawStats } from "../stats-types";

const NOTE = "These figures describe videos uploaded to this tool, not how common misinformation is online.";

/** The §7ah example: some cells suppressed, share null, median present. */
export const MOCK_STATS_30D: RawStats = {
  window: "30d",
  window_start: "2026-10-27T12:00:00+00:00",
  window_end: "2026-11-26T12:00:00+00:00",
  generated_at: "2026-11-26T12:00:00+00:00",
  cache_seconds: 60,
  min_cell: 5,
  note: NOTE,
  videos: {
    total: 30,
    per_week: [
      { week_start: "2026-10-26", videos: "<5" },
      { week_start: "2026-11-02", videos: "<5" },
      { week_start: "2026-11-09", videos: "<5" },
      { week_start: "2026-11-16", videos: "<5" },
      { week_start: "2026-11-23", videos: 19 },
    ],
  },
  jobs: { pending_now: 5, running_now: "<5", failed: 6 },
  labels: {
    MISINFO: 12,
    NO_MISINFO: 7,
    DEBUNKING: 5,
    CANNOT_RECOGNIZE: 6,
    misinfo_basis: { contradicted: 6, unproven: "<5", denies_supported: "<5", unspecified: "<5" },
  },
  reviews: { backlog_now: "<5", decisions: 8, changed_label: "<5", kept_label: "<5", changed_label_share: null, median_hours_to_decision: 4.5 },
  top_categories: [
    { category: "treatment_efficacy", videos: 14 },
    { category: "prevention", videos: 6 },
  ],
};

/** Enough decisions: share and median shown; every cell published. */
export const MOCK_STATS_ALL: RawStats = {
  ...MOCK_STATS_30D,
  window: "all",
  window_start: null,
  videos: {
    total: 120,
    per_week: [
      { week_start: "2026-11-09", videos: 40 },
      { week_start: "2026-11-16", videos: 35 },
      { week_start: "2026-11-23", videos: 45 },
    ],
  },
  labels: {
    MISINFO: 50,
    NO_MISINFO: 40,
    DEBUNKING: 15,
    CANNOT_RECOGNIZE: 15,
    misinfo_basis: { contradicted: 25, unproven: 15, denies_supported: 5, unspecified: 5 },
  },
  reviews: { backlog_now: 9, decisions: 40, changed_label: 10, kept_label: 30, changed_label_share: 0.25, median_hours_to_decision: 6.2 },
  top_categories: [
    { category: "treatment_efficacy", videos: 60 },
    { category: "evidence_meta", videos: 12 },
    { category: "some_new_category", videos: 5 },
  ],
};

/** A quiet week: the total is hidden, so every group summing to it is hidden too. */
export const MOCK_STATS_7D_SMALL: RawStats = {
  ...MOCK_STATS_30D,
  window: "7d",
  window_start: "2026-11-19T12:00:00+00:00",
  videos: { total: "<5", per_week: [{ week_start: "2026-11-16", videos: "<5" }, { week_start: "2026-11-23", videos: "<5" }] },
  jobs: { pending_now: "<5", running_now: "<5", failed: "<5" },
  labels: {
    MISINFO: "<5",
    NO_MISINFO: "<5",
    DEBUNKING: "<5",
    CANNOT_RECOGNIZE: "<5",
    misinfo_basis: { contradicted: "<5", unproven: "<5", denies_supported: "<5", unspecified: "<5" },
  },
  reviews: { backlog_now: "<5", decisions: "<5", changed_label: "<5", kept_label: "<5", changed_label_share: null, median_hours_to_decision: null },
  top_categories: [],
};
