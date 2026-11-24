"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ErrorBanner,
  Icon,
  LabelBadge,
  ReviewReasonChip,
  SeverityTag,
  StanceChip,
  VerdictChip,
  buttonClass,
} from "@/components/ui";
import { TONE } from "@/components/ui/tone";
import { SourceCard, sortSources } from "@/components/result/SourceCard";
import { clock, type Claim, type ResultModel } from "@/lib/api/result-adapter";
import type { CaseModel } from "@/lib/api/review-adapter";
import {
  DECISIONS,
  EMPTY_FORM,
  NOTE_MIN,
  REASON_CODES,
  decisionRequest,
  disagreements,
  isValid,
  labelFromClaims,
  mismatchWarning,
  needsBlindStep,
  validateDecision,
  type DecisionForm,
  type PreReveal,
  type ReasonCode,
} from "@/lib/review/decision";
import {
  LABELS,
  SEVERITIES,
  STANCES,
  STANCE_VALUES,
  VERDICTS,
  VERDICT_VALUES,
  VIDEO_LABELS,
  type Severity,
  type Stance,
  type Verdict,
  type VideoLabel,
} from "@/lib/vocabulary";

export type SubmitResult = { ok: true } | { ok: false; message: string };

type Props = {
  review: CaseModel;
  result: ResultModel | null;
  onDecide: (req: ReturnType<typeof decisionRequest>) => Promise<SubmitResult>;
  onOverrideSeverity: (claimId: string, severity: Severity, reason: string) => Promise<SubmitResult>;
};

/**
 * Review workspace (ReviewWorkspace.dc.html; ReviewV3.dc.html for HIGH priority).
 * Evidence first. On HIGH cases the reviewer records their own stance and verdict
 * before the system's assessment is shown (Q1); both are kept.
 */
export function ReviewWorkspace({ review, result, onDecide, onOverrideSeverity }: Props) {
  const blind = needsBlindStep({ severity: review.severity });
  const claims = useMemo(() => result?.claims ?? [], [result]);
  const judged = useMemo(() => (result?.decidingClaims.length ? result.decidingClaims : claims), [result, claims]);

  const [mine, setMine] = useState<Record<string, { stance?: Stance; verdict?: Verdict }>>({});
  const [preReveal, setPreReveal] = useState<PreReveal[] | null>(null);
  const revealed = !blind || preReveal !== null;

  const [form, setForm] = useState<DecisionForm>(EMPTY_FORM);
  const [touched, setTouched] = useState(false);
  const [sending, setSending] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const readOnly = !review.open || review.isOwn || done;
  const ctx = {
    proposedLabel: review.proposedLabel,
    severity: review.severity,
    preReveal,
    isOwnSubmission: review.isOwn,
    alreadyDecided: !review.open || done,
  };
  const errors = validateDecision(form, ctx);
  const show = (k: keyof typeof errors) => (touched ? errors[k] : undefined);

  const correctedClaims = claims.map((c) => {
    const fix = form.claimCorrections.find((x) => x.claimId === c.id);
    return { stance: fix?.stance ?? c.stance, verdict: fix?.verdict ?? c.verdict };
  });
  const warning = mismatchWarning(form, labelFromClaims(correctedClaims));

  const commitReady = judged.length > 0 && judged.every((c) => mine[c.id]?.stance && mine[c.id]?.verdict);
  function commit() {
    setPreReveal(judged.map((c) => ({ claimId: c.id, stance: mine[c.id].stance!, verdict: mine[c.id].verdict! })));
  }

  async function submit() {
    setTouched(true);
    setServerError(null);
    if (!isValid(errors)) {
      document.getElementById("decision")?.scrollIntoView({ block: "start" });
      return;
    }
    setSending(true);
    const res = await onDecide(decisionRequest(form, preReveal));
    setSending(false);
    if (res.ok) setDone(true);
    else setServerError(res.message);
  }

  const setFix = (claimId: string, patch: { stance?: Stance; verdict?: Verdict }) =>
    setForm((f) => {
      const rest = f.claimCorrections.filter((x) => x.claimId !== claimId);
      const cur = f.claimCorrections.find((x) => x.claimId === claimId) ?? { claimId };
      return { ...f, claimCorrections: [...rest, { ...cur, ...patch }] };
    });

  const submitText = DECISIONS.find((d) => d.kind === form.kind)?.submit ?? "Save decision";

  const showBar = revealed && !readOnly;
  return (
    <div className={`flex flex-col gap-5 ${showBar ? "pb-20 sm:pb-24 xl:pb-0" : ""}`}>
      {showBar && (
        // ReviewTablet.dc.html: below 1280 px the form is under the evidence, so a bar
        // keeps the decision and Save in reach. Content is padded so it never covers
        // the focused element (WCAG 2.4.11).
        <div className="fixed inset-x-0 bottom-0 z-30 hidden items-center gap-3 border-t border-line bg-surface px-4 py-3 shadow-3 sm:flex xl:hidden">
          <p className="flex-1 text-small text-ink">
            {form.kind ? (
              <>
                <span className="font-semibold">{DECISIONS.find((d) => d.kind === form.kind)?.title}</span>
                {form.kind === "CORRECT" && form.correctedLabel ? <> → {LABELS[form.correctedLabel].display}</> : null}
              </>
            ) : (
              <span className="text-ink-2">No decision yet</span>
            )}
          </p>
          <a href="#decision" className={buttonClass("secondary", "sm")}>Go to the form</a>
          <button type="button" onClick={submit} disabled={sending} className={buttonClass("primary", "sm")}>
            {sending ? "Saving…" : "Save"}
          </button>
        </div>
      )}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-small text-ink-2">
        <Link href="/review" className="text-primary hover:underline">Review queue</Link>
        <Icon name="chevr" className="!h-3.5 !w-3.5" />
        <span className="font-mono">{review.filename}</span>
      </nav>

      <header className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-h2 text-ink">{review.filename}</h1>
          {review.severity && <SeverityTag severity={review.severity} />}
          <span className="text-small text-ink-2">Waiting {review.waiting}</span>
          {review.submittedBy && <span className="text-small text-ink-2">· {review.isOwn ? "You submitted this video" : `Submitted by ${review.submittedBy}`}</span>}
          {revealed && (
            <Link href={`/jobs/${review.jobId}`} className="ml-auto text-small text-primary underline">Open the full result</Link>
          )}
        </div>
        {/* The reasons describe the system's reading, so on HIGH cases they wait for the reveal too. */}
        {revealed ? (
          <div className="flex flex-wrap gap-2">
            {review.reasons.map((r) => (
              <ReviewReasonChip key={r.rule} code={r.rule} text={r.text} />
            ))}
          </div>
        ) : (
          <p className="text-small text-ink-2">Why the system sent this case, and its assessment, appear after you record your own judgement.</p>
        )}
      </header>

      {review.isOwn && review.open && (
        <ErrorBanner title="Your submission. Another reviewer decides.">You can read this case, but you can&apos;t decide it.</ErrorBanner>
      )}
      {review.decision && (
        <section aria-label="Decision" className="rounded-lg border border-line bg-surface-2 p-4 text-small text-ink">
          <p className="font-semibold">
            {review.decision.actionText} by {review.decision.by}
            {review.decision.at ? `, ${new Date(review.decision.at).toLocaleString()}` : ""}
          </p>
          {review.decision.correctedLabel && (
            <p className="mt-1 flex items-center gap-2">New label: <LabelBadge label={review.decision.correctedLabel} /></p>
          )}
          {review.decision.reason && <p className="mt-1 text-ink-2">{review.decision.reason}</p>}
        </section>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        {/* Evidence first */}
        <section aria-labelledby="ev-h" className="flex flex-col gap-4">
          <h2 id="ev-h" className="text-h2 text-ink">The evidence</h2>
          {!result && <p className="text-small text-ink-2">The claims and sources for this video couldn&apos;t be loaded.</p>}
          {claims.map((c) => (
            <EvidenceClaim key={c.id} claim={c} showSystem={revealed} />
          ))}
        </section>

        <aside aria-labelledby="dec-h" className="flex flex-col gap-4 xl:sticky xl:top-4">
          {!readOnly && (
            <p className="rounded-lg border border-line bg-surface-2 p-4 text-small text-ink-2 sm:hidden">
              Reviewing needs a tablet or a larger screen. You can read the case here.
            </p>
          )}
          {blind && (
            <section aria-labelledby="s1-h" className="hidden flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-1 sm:flex">
              <div>
                <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">Step 1 of 2</p>
                <h2 id="s1-h" className="text-h2 text-ink">Your judgement first</h2>
                <p className="text-small text-ink-2">High-priority cases ask for your reading before you see the system&apos;s. Both are kept.</p>
              </div>
              {judged.map((c) => (
                <fieldset key={c.id} disabled={preReveal !== null || readOnly} className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3">
                  <legend className="px-1 text-small font-semibold text-ink">Claim {c.number}</legend>
                  <p className="font-serif text-small text-ink">{c.text}</p>
                  <Select
                    id={`mine-st-${c.id}`}
                    label="The speaker"
                    value={mine[c.id]?.stance ?? ""}
                    options={STANCE_VALUES.map((s) => [s, `${STANCES[s].display}: ${STANCES[s].description}`])}
                    onChange={(v) => setMine((m) => ({ ...m, [c.id]: { ...m[c.id], stance: v as Stance } }))}
                  />
                  <Select
                    id={`mine-v-${c.id}`}
                    label="The evidence"
                    value={mine[c.id]?.verdict ?? ""}
                    options={VERDICT_VALUES.map((v) => [v, VERDICTS[v].display])}
                    onChange={(v) => setMine((m) => ({ ...m, [c.id]: { ...m[c.id], verdict: v as Verdict } }))}
                  />
                </fieldset>
              ))}
              {preReveal === null ? (
                <button type="button" disabled={!commitReady || readOnly} onClick={commit} className={buttonClass("primary")}>
                  Commit and show system assessment
                </button>
              ) : (
                <Comparison mine={preReveal} claims={judged} />
              )}
              {touched && errors.preReveal && <p className="text-small text-err-fg">{errors.preReveal}</p>}
            </section>
          )}

          <section id="decision" aria-labelledby="dec-h" className="hidden scroll-mt-4 flex-col gap-4 rounded-lg border border-line bg-surface p-4 shadow-1 sm:flex">
            <div>
              {blind && <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">Step 2 of 2</p>}
              <h2 id="dec-h" className="text-h2 text-ink">Your decision</h2>
            </div>
            {revealed && review.proposedLabel && (
              <p className="flex flex-wrap items-center gap-2 text-small text-ink-2">
                System label: <LabelBadge label={review.proposedLabel} />
              </p>
            )}

            <fieldset disabled={readOnly || !revealed} className="flex flex-col gap-2">
              <legend className="mb-1 text-small font-semibold text-ink">Decision <span aria-hidden="true">*</span></legend>
              {DECISIONS.map((d) => (
                <label key={d.kind} className={`flex cursor-pointer gap-3 rounded-md border p-3 ${form.kind === d.kind ? "border-primary bg-primary-subtle" : "border-line-input"}`}>
                  <input type="radio" name="decision" value={d.kind} checked={form.kind === d.kind} onChange={() => setForm((f) => ({ ...f, kind: d.kind }))} className="mt-1" />
                  <span>
                    <span className="block text-small font-semibold text-ink">{d.title}</span>
                    <span className="block text-cap text-ink-2">{d.description}</span>
                  </span>
                </label>
              ))}
              {show("kind") && <p className="text-small text-err-fg">{errors.kind}</p>}
            </fieldset>

            {form.kind === "CORRECT" && (
              <>
                <fieldset disabled={readOnly} className="flex flex-col gap-2">
                  <legend className="mb-1 text-small font-semibold text-ink">New label <span aria-hidden="true">*</span></legend>
                  <div className="grid grid-cols-2 gap-2">
                    {VIDEO_LABELS.map((l) => (
                      <label key={l} className={`flex cursor-pointer items-center gap-2 rounded-md border p-2 ${form.correctedLabel === l ? "border-primary" : "border-line-input"}`}>
                        <input type="radio" name="label" value={l} checked={form.correctedLabel === l} onChange={() => setForm((f) => ({ ...f, correctedLabel: l as VideoLabel }))} />
                        <LabelBadge label={l} />
                        <span className="sr-only">{LABELS[l].description}</span>
                      </label>
                    ))}
                  </div>
                  {show("correctedLabel") && <p className="text-small text-err-fg">{errors.correctedLabel}</p>}
                </fieldset>
                <details className="rounded-md border border-line p-3">
                  <summary className="cursor-pointer text-small font-semibold text-ink">Correct a claim (optional)</summary>
                  <p className="mt-1 text-cap text-ink-2">Correcting claims doesn&apos;t recompute the label.</p>
                  {claims.map((c) => {
                    const fix = form.claimCorrections.find((x) => x.claimId === c.id);
                    return (
                      <div key={c.id} className="mt-3 flex flex-col gap-2 border-t border-line pt-3">
                        <p className="text-small font-semibold text-ink">Claim {c.number}</p>
                        <Select id={`fix-st-${c.id}`} label="Stance" value={fix?.stance ?? c.stance ?? ""} options={STANCE_VALUES.map((s) => [s, STANCES[s].display])} onChange={(v) => setFix(c.id, { stance: v as Stance })} />
                        <Select id={`fix-v-${c.id}`} label="Evidence verdict" value={fix?.verdict ?? c.verdict ?? ""} options={VERDICT_VALUES.map((v) => [v, VERDICTS[v].display])} onChange={(v) => setFix(c.id, { verdict: v as Verdict })} />
                      </div>
                    );
                  })}
                </details>
                {warning && (
                  <p role="status" className="flex gap-2 rounded-md border border-warn-bd bg-warn-bg p-3 text-small text-warn-fg">
                    <Icon name="alert" className="mt-0.5 !h-3.5 !w-3.5" /> {warning}
                  </p>
                )}
              </>
            )}

            <Select
              id="reason-code"
              label="Reason"
              required
              disabled={readOnly || !revealed}
              value={form.reasonCode ?? ""}
              options={REASON_CODES.map((r) => [r.code, r.text])}
              onChange={(v) => setForm((f) => ({ ...f, reasonCode: v as ReasonCode }))}
              error={show("reasonCode")}
            />
            <div className="flex flex-col gap-1.5">
              <label htmlFor="note" className="text-small font-semibold text-ink">
                Note <span aria-hidden="true">*</span>
              </label>
              <textarea
                id="note"
                rows={4}
                required
                disabled={readOnly || !revealed}
                aria-invalid={show("note") ? true : undefined}
                aria-describedby="note-hint"
                value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                className={`w-full rounded-md border bg-surface px-3 py-2 text-body text-ink ${show("note") ? "border-err-fg" : "border-line-input"}`}
              />
              <p id="note-hint" className="text-cap text-ink-3">
                At least {NOTE_MIN} characters. Saved with your name in the audit trail and shown on exports. ({form.note.trim().length})
              </p>
              {show("note") && <p className="text-small text-err-fg">{errors.note}</p>}
            </div>

            {(show("form") || serverError) && (
              <p role="alert" className="rounded-md border border-err-bd bg-err-bg px-3 py-2 text-small text-err-fg">
                {serverError ?? errors.form}
              </p>
            )}
            {done ? (
              <p role="status" className="rounded-md border border-nomisinfo-bd bg-primary-subtle px-3 py-2 text-small text-ink">
                Decision saved. <Link href="/review" className="text-primary underline">Back to the queue</Link>
              </p>
            ) : (
              <button type="button" onClick={submit} disabled={readOnly || !revealed || sending} className={buttonClass("primary")}>
                {sending ? "Saving…" : submitText}
              </button>
            )}
          </section>

          {revealed && !readOnly && claims.length > 0 && (
            <div className="hidden sm:block">
              <SeverityOverride claims={claims} onSave={onOverrideSeverity} />
            </div>
          )}

          <section aria-labelledby="audit-h" className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
            <h2 id="audit-h" className="text-h3 text-ink">Audit trail</h2>
            {review.audit.length === 0 ? (
              <p className="text-small text-ink-2">No actions recorded yet.</p>
            ) : (
              <ol className="flex flex-col gap-2">
                {review.audit.map((a) => (
                  <li key={a.id} className="border-l-2 border-line-input pl-3 text-small">
                    <p className="text-ink">
                      <span className="font-semibold">{a.who}</span> · {a.what}
                    </p>
                    <p className="text-cap text-ink-3">{new Date(a.when).toLocaleString()}</p>
                    {a.reason && <p className="text-ink-2">{a.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
            <p className="text-cap text-ink-3">Entries can&apos;t be edited or removed.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function EvidenceClaim({ claim: c, showSystem }: { claim: Claim; showSystem: boolean }) {
  const sources = sortSources(c.sources);
  return (
    <article aria-labelledby={`rv-${c.id}`} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-1">
      <header className="flex flex-wrap items-center gap-2">
        <h3 id={`rv-${c.id}`} className="text-h3 text-ink">Claim {c.number}</h3>
        <span className="font-mono text-small text-ink-2">{clock(c.start)}–{clock(c.end)}</span>
        {c.deciding && <span className="rounded-sm bg-ink px-1.5 text-cap font-semibold text-bg">Decided the label</span>}
      </header>
      <p className="font-serif text-[17px] leading-[26px] text-ink">{c.text}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h4 className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the speaker said</h4>
          {c.quotes.length === 0 && <p className="text-small text-ink-2">No quoted words were stored.</p>}
          {c.quotes.map((q) => (
            <p key={`${q.source}-${q.id}`} className="rounded-md border-l-2 border-line-input bg-surface-2 px-3 py-2 text-small text-ink">
              <q>{q.text}</q> <span className="font-mono text-cap text-ink-3">{q.source === "screen" ? "on screen, " : ""}{clock(q.start)}</span>
            </p>
          ))}
          {showSystem && c.stance && (
            <p className="flex flex-wrap items-center gap-2 text-small text-ink-2">System: <StanceChip stance={c.stance} /></p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <h4 className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the sources say</h4>
          {sources.length === 0 && <p className="text-small text-ink-2">No source was found that tests this claim.</p>}
          {sources.map((s) => (
            <SourceCard key={s.id} s={s} />
          ))}
          {showSystem && c.verdict && (
            <p className="flex flex-wrap items-center gap-2 text-small text-ink-2">System: <VerdictChip verdict={c.verdict} /></p>
          )}
        </div>
      </div>
    </article>
  );
}

function Comparison({ mine, claims }: { mine: PreReveal[]; claims: Claim[] }) {
  const diff = disagreements(mine, claims.map((c) => ({ claimId: c.id, stance: c.stance, verdict: c.verdict })));
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-h3 text-ink">You and the system</h3>
      <table className="w-full border-collapse text-small">
        <thead>
          <tr className="border-b border-line text-left text-ink-2">
            <th scope="col" className="py-1.5 font-semibold">Claim</th>
            <th scope="col" className="py-1.5 font-semibold">You</th>
            <th scope="col" className="py-1.5 font-semibold">System</th>
          </tr>
        </thead>
        <tbody>
          {mine.map((m) => {
            const c = claims.find((x) => x.id === m.claimId);
            return (
              <tr key={m.claimId} className="border-b border-line align-top">
                <th scope="row" className="py-2 pr-2 font-semibold">{c?.number ?? "?"}</th>
                <td className="flex flex-col gap-1 py-2 pr-2"><StanceChip stance={m.stance} /><VerdictChip verdict={m.verdict} /></td>
                <td className="py-2">
                  <span className="flex flex-col gap-1">
                    {c?.stance ? <StanceChip stance={c.stance} /> : "Not assessed"}
                    {c?.verdict ? <VerdictChip verdict={c.verdict} /> : "Not checked"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {diff.length > 0 ? (
        <p role="status" className={`flex gap-2 rounded-md border p-3 text-small ${TONE.mixed}`}>
          <Icon name="alert" className="mt-0.5 !h-3.5 !w-3.5" />
          You and the system disagree on {diff.map((d) => `claim ${claims.find((c) => c.id === d.claimId)?.number}`).join(", ")}. Say which reading you&apos;re keeping and why.
        </p>
      ) : (
        <p className="text-small text-ink-2">You and the system agree.</p>
      )}
    </div>
  );
}

function SeverityOverride({ claims, onSave }: { claims: Claim[]; onSave: Props["onOverrideSeverity"] }) {
  const [claimId, setClaimId] = useState(claims[0].id);
  const [severity, setSeverity] = useState<Severity | "">("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const err = !severity ? "Choose a priority." : reason.trim().length < NOTE_MIN ? `Write at least ${NOTE_MIN} characters.` : null;
  return (
    <details className="rounded-lg border border-line bg-surface p-4">
      <summary className="cursor-pointer text-h3 text-ink">Change a claim&apos;s priority</summary>
      <p className="mt-1 text-cap text-ink-2">Priority only orders the queue. It never changes a label or verdict.</p>
      <div className="mt-3 flex flex-col gap-3">
        <Select id="sev-claim" label="Claim" value={claimId} options={claims.map((c) => [c.id, `Claim ${c.number}`])} onChange={setClaimId} />
        <Select id="sev-level" label="New priority" value={severity} options={SEVERITIES.map((s) => [s, s === "HIGH" ? "High" : s === "MEDIUM" ? "Medium" : "Low"])} onChange={(v) => setSeverity(v as Severity)} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="sev-reason" className="text-small font-semibold text-ink">Reason <span aria-hidden="true">*</span></label>
          <textarea id="sev-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded-md border border-line-input bg-surface px-3 py-2 text-body" />
        </div>
        {touched && err && <p className="text-small text-err-fg">{err}</p>}
        {msg && <p role="status" className="text-small text-ink-2">{msg}</p>}
        <button
          type="button"
          className={buttonClass("secondary", "sm")}
          onClick={async () => {
            setTouched(true);
            if (err || !severity) return;
            const res = await onSave(claimId, severity, reason.trim());
            setMsg(res.ok ? "Priority changed. It's in the audit trail." : res.message);
          }}
        >
          Save priority
        </button>
      </div>
    </details>
  );
}

function Select(props: {
  id: string;
  label: string;
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
  required?: boolean;
  disabled?: boolean;
  error?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={props.id} className="text-small font-semibold text-ink">
        {props.label} {props.required && <span aria-hidden="true">*</span>}
      </label>
      <select
        id={props.id}
        value={props.value}
        required={props.required}
        disabled={props.disabled}
        aria-invalid={props.error ? true : undefined}
        onChange={(e) => props.onChange(e.target.value)}
        className={`min-h-10 w-full min-w-0 rounded-md border bg-surface px-3 text-body text-ink ${props.error ? "border-err-fg" : "border-line-input"}`}
      >
        <option value="" disabled>
          Choose…
        </option>
        {props.options.map(([v, t]) => (
          <option key={v} value={v}>
            {t}
          </option>
        ))}
      </select>
      {props.error && <p className="text-small text-err-fg">{props.error}</p>}
    </div>
  );
}
