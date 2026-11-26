// Raw shapes of GET /v1/admin/evals (T63 backend, context/MULTI_AGENT.md §7ag).
// Records follow evals/eval_record.schema.json, plus `step_index` and `report_url`.

export type RawModelRef = { provider?: string | null; model: string; prompt?: string | null; role?: string | null };

export type RawCI95 = { low: number; high: number; method?: string | null };

export type RawEvalRecord = {
  schema_version?: string;
  run_id: string;
  run_group?: string | null;
  date: string;
  task: string;
  pipeline_step: string;
  step_index?: number;
  split: "tune" | "test" | null;
  synthetic: boolean;
  golden_set_ref: string | null;
  models: RawModelRef[] | null;
  variant?: string | null;
  metric_name: string;
  value: number | null;
  ci95: RawCI95 | null;
  n_items: number | null;
  n_unit?: string | null;
  cost_usd: number | null;
  report_path: string;
  report_url?: string | null;
  notes?: string;
};

export type RawEvalGroup = { step: string; step_index: number; count: number; run_ids: string[] };

export type RawEvalsResponse = { total: number; step_order: string[]; groups: RawEvalGroup[]; items: RawEvalRecord[] };
