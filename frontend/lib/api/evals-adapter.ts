// Adapter for GET /v1/admin/evals (T63). Values are shown as the registry has them,
// never recomputed (§7ag: they are copied from the reports).
import { stepDisplay, type EvalSplit } from "@/lib/vocabulary";
import type { RawEvalRecord, RawEvalsResponse } from "./evals-types";

export type EvalModel = { model: string; provider: string | null; prompt: string | null; role: string | null };

export type EvalRun = {
  runId: string;
  runGroup: string | null;
  /** Records in the list that share this run group; `costUsd` is for the whole group. */
  groupSize: number;
  date: string;
  task: string;
  step: string;
  stepLabel: string;
  stepIndex: number;
  split: EvalSplit;
  synthetic: boolean;
  goldenSetRef: string | null;
  /** [] = no model ran; null = the report doesn't say. */
  models: EvalModel[] | null;
  variant: string | null;
  metric: string;
  value: number | null;
  ci: { low: number; high: number; method: string | null } | null;
  nItems: number | null;
  nUnit: string | null;
  costUsd: number | null;
  reportPath: string;
  /** Only an http(s) link is kept. */
  reportUrl: string | null;
  notes: string;
};

export type EvalsModel = { total: number; stepOrder: string[]; runs: EvalRun[] };

function safeUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const p = new URL(u);
    return p.protocol === "https:" || p.protocol === "http:" ? p.toString() : null;
  } catch {
    return null;
  }
}

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function adaptEvalRecord(r: RawEvalRecord, stepOrder: string[], groupSizes: Map<string, number>): EvalRun {
  const idx = r.step_index ?? stepOrder.indexOf(r.pipeline_step);
  return {
    runId: r.run_id,
    runGroup: r.run_group ?? null,
    groupSize: r.run_group ? groupSizes.get(r.run_group) ?? 1 : 1,
    date: r.date,
    task: r.task,
    step: r.pipeline_step,
    stepLabel: stepDisplay(r.pipeline_step),
    stepIndex: idx >= 0 ? idx : Number.MAX_SAFE_INTEGER,
    split: r.split === "tune" || r.split === "test" ? r.split : "none",
    synthetic: r.synthetic === true,
    goldenSetRef: r.golden_set_ref ?? null,
    models:
      r.models === null || r.models === undefined
        ? null
        : r.models.map((m) => ({ model: m.model, provider: m.provider ?? null, prompt: m.prompt ?? null, role: m.role ?? null })),
    variant: r.variant ?? null,
    metric: r.metric_name,
    value: finite(r.value) ? r.value : null,
    ci: r.ci95 && finite(r.ci95.low) && finite(r.ci95.high) ? { low: r.ci95.low, high: r.ci95.high, method: r.ci95.method ?? null } : null,
    nItems: r.n_items ?? null,
    nUnit: r.n_unit ?? null,
    costUsd: finite(r.cost_usd) ? r.cost_usd : null,
    reportPath: r.report_path,
    reportUrl: safeUrl(r.report_url),
    notes: r.notes ?? "",
  };
}

export function adaptEvals(raw: RawEvalsResponse): EvalsModel {
  const items = raw.items ?? [];
  const stepOrder = raw.step_order ?? [];
  const groupSizes = new Map<string, number>();
  for (const r of items) if (r.run_group) groupSizes.set(r.run_group, (groupSizes.get(r.run_group) ?? 0) + 1);
  return { total: raw.total ?? items.length, stepOrder, runs: items.map((r) => adaptEvalRecord(r, stepOrder, groupSizes)) };
}

// ---------------------------------------------------------------- filters and order

export type EvalFilters = { task: string | null; step: string | null; split: EvalSplit | null };
export type EvalOrder = "step" | "newest";

export const NO_FILTERS: EvalFilters = { task: null, step: null, split: null };

export function filterEvals(runs: EvalRun[], f: EvalFilters): EvalRun[] {
  return runs.filter((r) => (!f.task || r.task === f.task) && (!f.step || r.step === f.step) && (!f.split || r.split === f.split));
}

const byDateDesc = (a: EvalRun, b: EvalRun) => (a.date === b.date ? a.runId.localeCompare(b.runId) : a.date < b.date ? 1 : -1);

/** "step": pipeline order, newest first within a step (the API's order). "newest": by date only. */
export function sortEvals(runs: EvalRun[], order: EvalOrder): EvalRun[] {
  const copy = [...runs];
  if (order === "newest") return copy.sort(byDateDesc);
  return copy.sort((a, b) => a.stepIndex - b.stepIndex || byDateDesc(a, b));
}

/** Consecutive runs of the same step, for the grouped view. Input must be sorted by step. */
export function groupByStep(runs: EvalRun[]): { step: string; label: string; runs: EvalRun[] }[] {
  const out: { step: string; label: string; runs: EvalRun[] }[] = [];
  for (const r of runs) {
    const last = out[out.length - 1];
    if (last && last.step === r.step) last.runs.push(r);
    else out.push({ step: r.step, label: r.stepLabel, runs: [r] });
  }
  return out;
}

/** Task ids in number order (T5 before T38). */
export function taskOptions(runs: EvalRun[]): string[] {
  const num = (t: string) => Number(t.replace(/\D/g, "")) || 0;
  return Array.from(new Set(runs.map((r) => r.task))).sort((a, b) => num(a) - num(b) || a.localeCompare(b));
}

/** Steps present, in pipeline order. */
export function stepOptions(runs: EvalRun[]): { step: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const r of sortEvals(runs, "step")) if (!seen.has(r.step)) seen.set(r.step, r.stepLabel);
  return Array.from(seen, ([step, label]) => ({ step, label }));
}

// ---------------------------------------------------------------- display

/** As reported, at most 4 decimals: 0.6759 → "0.6759", 0.68 → "0.68", 12 → "12". */
export function formatValue(v: number | null): string {
  if (v === null) return "Not computed";
  return String(Number(v.toFixed(4)));
}

export function formatCost(usd: number | null): string {
  if (usd === null) return "Not recorded";
  if (usd === 0) return "$0 (no paid calls)";
  return `$${usd.toFixed(2)}`;
}

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
