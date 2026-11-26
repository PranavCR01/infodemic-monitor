// Raw shape of GET /v1/stats (T62 backend, context/MULTI_AGENT.md §7ah).
// A cell is an integer >= 5, or the string "<5" (zero included).

export type RawCell = number | "<5";

export type RawStats = {
  window: "7d" | "30d" | "90d" | "all";
  window_start: string | null;
  window_end: string;
  generated_at: string;
  cache_seconds?: number;
  min_cell?: number;
  note?: string;
  videos: { total: RawCell; per_week: { week_start: string; videos: RawCell }[] };
  jobs: { pending_now: RawCell; running_now: RawCell; failed: RawCell };
  labels: {
    MISINFO: RawCell;
    NO_MISINFO: RawCell;
    DEBUNKING: RawCell;
    CANNOT_RECOGNIZE: RawCell;
    misinfo_basis: { contradicted: RawCell; unproven: RawCell; denies_supported: RawCell; unspecified: RawCell };
  };
  reviews: {
    backlog_now: RawCell;
    decisions: RawCell;
    changed_label: RawCell;
    kept_label: RawCell;
    changed_label_share: number | null;
    median_hours_to_decision: number | null;
  };
  top_categories: { category: string; videos: RawCell }[];
};
