"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Button, EmptyState, Icon } from "@/components/ui";
import {
  filterEvals,
  formatCost,
  formatDate,
  formatValue,
  groupByStep,
  NO_FILTERS,
  sortEvals,
  stepOptions,
  taskOptions,
  type EvalFilters,
  type EvalOrder,
  type EvalRun,
} from "@/lib/api/evals-adapter";
import { EVAL_SPLIT_DISPLAY, SYNTHETIC_DISPLAY, type EvalSplit } from "@/lib/vocabulary";

type Props = { runs: EvalRun[] };

const SPLITS: EvalSplit[] = ["tune", "test", "none"];

/** T63: every recorded evaluation result, admin only. Numbers are the reports' own. */
export function EvalsList({ runs }: Props) {
  const [f, setF] = useState<EvalFilters>(NO_FILTERS);
  const [order, setOrder] = useState<EvalOrder>("step");
  const tasks = useMemo(() => taskOptions(runs), [runs]);
  const steps = useMemo(() => stepOptions(runs), [runs]);
  const shown = useMemo(() => sortEvals(filterEvals(runs, f), order), [runs, f, order]);
  const filtered = f.task !== null || f.step !== null || f.split !== null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-h1 text-ink">Evaluations</h1>
        <p className="max-w-prose text-small text-ink-2">
          Every recorded measurement of the pipeline, copied from its report. Tune-split results are development numbers, not product
          accuracy. Synthetic results show how a step works, not how accurate it is.
        </p>
      </div>

      {runs.length === 0 ? (
        <EmptyState icon="chart" title="No evaluations recorded yet">
          Results appear here once an evaluation task adds its record to the registry.
        </EmptyState>
      ) : (
        <>
          <form role="search" aria-label="Filter evaluations" className="flex flex-wrap items-end gap-3" onSubmit={(e) => e.preventDefault()}>
            <Select id="evals-task" label="Task" value={f.task ?? ""} onChange={(v) => setF({ ...f, task: v || null })}>
              <option value="">All tasks</option>
              {tasks.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <Select id="evals-step" label="Pipeline step" value={f.step ?? ""} onChange={(v) => setF({ ...f, step: v || null })}>
              <option value="">All steps</option>
              {steps.map((s) => (
                <option key={s.step} value={s.step}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Select id="evals-split" label="Split" value={f.split ?? ""} onChange={(v) => setF({ ...f, split: (v || null) as EvalSplit | null })}>
              <option value="">All splits</option>
              {SPLITS.map((s) => (
                <option key={s} value={s}>
                  {EVAL_SPLIT_DISPLAY[s].short}
                </option>
              ))}
            </Select>
            <Select id="evals-order" label="Order" value={order} onChange={(v) => setOrder(v as EvalOrder)}>
              <option value="step">By pipeline step</option>
              <option value="newest">Newest first</option>
            </Select>
            {filtered && (
              <Button variant="secondary" size="sm" className="min-h-10" onClick={() => setF(NO_FILTERS)}>
                Clear filters
              </Button>
            )}
          </form>

          <p className="text-small text-ink-2" role="status" aria-live="polite">
            {filtered ? `Showing ${shown.length} of ${runs.length} results` : `${runs.length} ${runs.length === 1 ? "result" : "results"}`}
          </p>

          {shown.length === 0 ? (
            <EmptyState icon="filter" title="No results match these filters" action={<Button variant="secondary" size="sm" onClick={() => setF(NO_FILTERS)}>Clear filters</Button>} />
          ) : order === "step" ? (
            groupByStep(shown).map((g) => (
              <section key={g.step} aria-labelledby={`step-${g.step}`} className="flex flex-col gap-3">
                <h2 id={`step-${g.step}`} className="flex flex-wrap items-baseline gap-2 text-h2 text-ink">
                  {g.label}
                  <span className="font-mono text-cap font-normal text-ink-3">{g.step}</span>
                  <span className="text-small font-normal tabular-nums text-ink-3">
                    · {g.runs.length} {g.runs.length === 1 ? "result" : "results"}
                  </span>
                </h2>
                <ul className="flex flex-col gap-3">
                  {g.runs.map((r) => (
                    <li key={r.runId}>
                      <EvalCard run={r} />
                    </li>
                  ))}
                </ul>
              </section>
            ))
          ) : (
            <ul className="flex flex-col gap-3" aria-label="Evaluation results, newest first">
              {shown.map((r) => (
                <li key={r.runId}>
                  <EvalCard run={r} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function Select({ id, label, value, onChange, children }: { id: string; label: string; value: string; onChange: (v: string) => void; children: ReactNode }) {
  return (
    <div className="flex min-w-[9rem] flex-1 flex-col gap-1.5 sm:flex-none">
      <label htmlFor={id} className="text-small font-semibold text-ink">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="min-h-10 w-full rounded-md border border-line-input bg-surface px-3 text-body text-ink">
        {children}
      </select>
    </div>
  );
}

export function SplitTag({ split }: { split: EvalSplit }) {
  const tone = split === "tune" ? "border-warn-bd bg-warn-bg text-warn-fg" : "border-line-input bg-surface-2 text-ink-2";
  return (
    <span data-split={split} className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-cap font-semibold ${tone}`}>
      {EVAL_SPLIT_DISPLAY[split].label}
    </span>
  );
}

function SyntheticTag() {
  return (
    <span data-synthetic="true" className="inline-flex items-center gap-1 rounded-sm border border-dashed border-err-fg px-2 py-0.5 text-cap font-semibold text-err-fg">
      <Icon name="alert" className="!h-3.5 !w-3.5" />
      {SYNTHETIC_DISPLAY}
    </span>
  );
}

function modelsText(r: EvalRun): ReactNode {
  if (r.models === null) return <span className="text-ink-3">Not recorded in the report</span>;
  if (r.models.length === 0) return <span className="text-ink-2">No model (rules only)</span>;
  return (
    <ul className="flex flex-col gap-0.5">
      {r.models.map((m, i) => (
        <li key={i}>
          <span className="font-mono">{m.model}</span>
          {m.provider && <span className="text-ink-3"> ({m.provider})</span>}
          {m.prompt ? (
            <>
              {" · prompt "}
              <span className="font-mono">{m.prompt}</span>
            </>
          ) : null}
          {m.role && <span className="text-ink-3"> · {m.role}</span>}
        </li>
      ))}
    </ul>
  );
}

function EvalCard({ run: r }: { run: EvalRun }) {
  const titleId = `eval-${r.runId}`;
  return (
    <article aria-labelledby={titleId} className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-1 [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 id={titleId} className="break-words font-mono text-small font-semibold text-ink">
            {r.metric}
          </h3>
          <p className="text-cap text-ink-3">
            {r.task} · {formatDate(r.date)}
            {r.variant && (
              <>
                {" · variant "}
                <span className="font-mono">{r.variant}</span>
              </>
            )}
          </p>
        </div>
        <div className="text-right">
          <p className="font-serif text-h1 tabular-nums text-ink">
            {formatValue(r.value)}
          </p>
          {r.ci && (
            <p className="text-cap tabular-nums text-ink-2" data-testid="ci">
              95% CI {formatValue(r.ci.low)} to {formatValue(r.ci.high)}
              {r.ci.method && <span className="block text-ink-3">{r.ci.method}</span>}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <SplitTag split={r.split} />
        {r.synthetic && <SyntheticTag />}
      </div>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-small sm:grid-cols-[max-content_1fr]">
        <Row term="Run">
          <span className="break-all font-mono">{r.runId}</span>
        </Row>
        <Row term="Pipeline step">
          {r.stepLabel} <span className="font-mono text-cap text-ink-3">({r.step})</span>
        </Row>
        <Row term="Golden set">{r.goldenSetRef ? <span className="break-all font-mono">{r.goldenSetRef}</span> : <span className="text-ink-3">None</span>}</Row>
        <Row term="Models and prompts">{modelsText(r)}</Row>
        <Row term="Items">
          {r.nItems === null ? <span className="text-ink-3">Not recorded</span> : <span className="tabular-nums">{r.nItems}</span>}
          {r.nItems !== null && r.nUnit && <span className="text-ink-2"> {r.nUnit}</span>}
        </Row>
        <Row term="Cost">
          <span className="tabular-nums">{formatCost(r.costUsd)}</span>
          {r.groupSize > 1 && r.costUsd !== null && r.costUsd > 0 && (
            <span className="text-ink-3"> for the whole run, shared by {r.groupSize} results here</span>
          )}
        </Row>
        <Row term="Report">
          {r.reportUrl ? (
            <a href={r.reportUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 break-all font-mono text-primary underline underline-offset-2">
              {r.reportPath}
              <Icon name="ext" className="!h-3.5 !w-3.5 shrink-0" />
              <span className="sr-only"> (opens GitHub in a new tab)</span>
            </a>
          ) : (
            <span className="break-all font-mono">{r.reportPath}</span>
          )}
        </Row>
      </dl>

      {r.notes && (
        <div className="border-t border-line pt-3 text-small">
          <p className="font-semibold text-ink">Notes</p>
          <p className="mt-1 whitespace-pre-line text-ink-2">{r.notes}</p>
        </div>
      )}
    </article>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="font-semibold text-ink-2">{term}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </>
  );
}
