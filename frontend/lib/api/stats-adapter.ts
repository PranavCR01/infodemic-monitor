// Adapter for GET /v1/stats (T62). Aggregates only: the response has no video, job,
// review or user id, and this model keeps none.
import {
  categoryDisplay,
  LABELS,
  MISINFO_BASIS_DISPLAY,
  type StatsWindow,
  type VideoLabel,
} from "@/lib/vocabulary";
import type { RawCell, RawStats } from "./stats-types";

/** The API's minimum published count (§7ah `min_cell`). */
export const MIN_CELL = 5;

/** A published count, or a suppressed one ("<5", zero included). Never a guessed number. */
export type Cell = { suppressed: false; n: number } | { suppressed: true };

/**
 * "<5" stays suppressed. A number under 5 should never arrive (the server suppresses
 * it), but if one does it is suppressed here too rather than shown.
 */
export function toCell(v: RawCell | null | undefined): Cell {
  if (typeof v === "number" && Number.isFinite(v) && v >= MIN_CELL) return { suppressed: false, n: Math.round(v) };
  return { suppressed: true };
}

export const cellText = (c: Cell): string => (c.suppressed ? "<5" : c.n.toLocaleString("en-GB"));
/** For screen readers: "fewer than 5" reads better than "<5". */
export const cellSpoken = (c: Cell): string => (c.suppressed ? "fewer than 5" : c.n.toLocaleString("en-GB"));

export type Row = { key: string; label: string; cell: Cell; hint?: string };

export type StatsModel = {
  window: StatsWindow;
  windowStart: string | null;
  windowEnd: string;
  generatedAt: string;
  videosTotal: Cell;
  perWeek: Row[];
  jobs: { pendingNow: Cell; runningNow: Cell; failed: Cell };
  labels: Row[];
  misinfoBasis: Row[];
  reviews: {
    backlogNow: Cell;
    decisions: Cell;
    changed: Cell;
    kept: Cell;
    /** 0..1, or null when there are too few decisions. */
    changedShare: number | null;
    medianHours: number | null;
  };
  categories: Row[];
};

const LABEL_ORDER: VideoLabel[] = ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"];
const BASIS_ORDER = ["contradicted", "unproven", "denies_supported", "unspecified"] as const;

export function weekLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return `Week of ${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}`;
}

const finiteOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function adaptStats(r: RawStats): StatsModel {
  return {
    window: r.window,
    windowStart: r.window_start ?? null,
    windowEnd: r.window_end,
    generatedAt: r.generated_at,
    videosTotal: toCell(r.videos?.total),
    perWeek: (r.videos?.per_week ?? []).map((w) => ({ key: w.week_start, label: weekLabel(w.week_start), cell: toCell(w.videos) })),
    jobs: { pendingNow: toCell(r.jobs?.pending_now), runningNow: toCell(r.jobs?.running_now), failed: toCell(r.jobs?.failed) },
    labels: LABEL_ORDER.map((l) => ({ key: l, label: LABELS[l].display, hint: LABELS[l].description, cell: toCell(r.labels?.[l]) })),
    misinfoBasis: BASIS_ORDER.map((b) => ({ key: b, label: MISINFO_BASIS_DISPLAY[b], cell: toCell(r.labels?.misinfo_basis?.[b]) })),
    reviews: {
      backlogNow: toCell(r.reviews?.backlog_now),
      decisions: toCell(r.reviews?.decisions),
      changed: toCell(r.reviews?.changed_label),
      kept: toCell(r.reviews?.kept_label),
      changedShare: finiteOrNull(r.reviews?.changed_label_share),
      medianHours: finiteOrNull(r.reviews?.median_hours_to_decision),
    },
    // §7ah: categories under 5 are left out by the server; drop any that slip through.
    categories: (r.top_categories ?? [])
      .map((c) => ({ key: c.category, label: categoryDisplay(c.category), cell: toCell(c.videos) }))
      .filter((c) => !c.cell.suppressed),
  };
}

/** Largest published count in a set of rows; suppressed cells never set the scale. */
export function scaleMax(rows: Row[]): number {
  return rows.reduce((m, r) => (r.cell.suppressed ? m : Math.max(m, r.cell.n)), 0);
}

export function formatShare(share: number | null): string | null {
  return share === null ? null : `${Math.round(share * 100)}%`;
}

export function formatHours(h: number | null): string | null {
  if (h === null) return null;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} minutes`;
  if (h >= 48) return `${(h / 24).toFixed(1)} days`;
  return `${h.toFixed(1)} hours`;
}
