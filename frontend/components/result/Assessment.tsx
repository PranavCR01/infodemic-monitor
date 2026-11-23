import { LabelBadge, ReviewStatusTag, StanceChip, VerdictChip, Icon, buttonClass } from "@/components/ui";
import { evidenceText, clock, type Claim, type ResultModel } from "@/lib/api/result-adapter";
import { DECISION_RULE_TEXT, EVIDENCE_LEVEL_DISPLAY, labelDisplay } from "@/lib/vocabulary";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** "System assessment" until a person confirms; then who-and-when (HANDOFF §1.5). */
function Provenance({ r }: { r: ResultModel }) {
  const human = r.reviewStatus === "VERIFIED" || r.reviewStatus === "CORRECTED";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-sm border border-line px-2 py-0.5 text-cap font-semibold text-ink-2">
      <Icon name={human ? "user" : "chart"} className="!h-3.5 !w-3.5" />
      {human
        ? `${r.reviewStatus === "VERIFIED" ? "Verified" : "Corrected"} by a reviewer${r.reviewDecidedAt ? `, ${formatDate(r.reviewDecidedAt)}` : ""}`
        : "System assessment"}
    </span>
  );
}

/** Deciding claim → stance → evidence → verdict → label (Direction 3 "How it was reached"). */
function Chain({ claim, r }: { claim: Claim; r: ResultModel }) {
  const quote = claim.quotes[0]?.text ?? claim.text;
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-small">
      <span className="font-mono text-ink-2">{clock(claim.start)}</span>
      <q className="font-serif text-ink">{quote}</q>
      <Icon name="chevr" className="!h-3.5 !w-3.5 text-ink-3" />
      {claim.stance && <StanceChip stance={claim.stance} />}
      <Icon name="chevr" className="!h-3.5 !w-3.5 text-ink-3" />
      <span className="text-ink-2">{evidenceText(claim.evidence, EVIDENCE_LEVEL_DISPLAY)}</span>
      <Icon name="chevr" className="!h-3.5 !w-3.5 text-ink-3" />
      {claim.verdict && <VerdictChip verdict={claim.verdict} />}
      <Icon name="chevr" className="!h-3.5 !w-3.5 text-ink-3" />
      {r.label && <LabelBadge label={r.label} basis={r.basis} />}
    </li>
  );
}

export function Assessment({ r }: { r: ResultModel }) {
  const shown = r.correctedLabel ?? r.label;
  // Q6: CANNOT RECOGNIZE keeps its name, with the reason underneath. For the other
  // labels the description already says it, so the rule line would repeat it.
  const ruleLine = shown === "CANNOT_RECOGNIZE" && r.decisionRule ? DECISION_RULE_TEXT[r.decisionRule] : null;
  return (
    <section aria-labelledby="assessment-h" className="flex flex-col gap-5 rounded-lg border border-line bg-surface p-6 shadow-1">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">Video</p>
          <h1 className="break-all font-mono text-h2 text-ink">{r.filename}</h1>
        </div>
        {r.label && (
          <a href={`/jobs/${encodeURIComponent(r.jobId)}/export`} className={buttonClass("secondary", "sm")}>
            <Icon name="download" className="!h-3.5 !w-3.5" /> Export report
          </a>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h2 id="assessment-h" className="text-cap font-semibold uppercase tracking-wider text-ink-3">
          Assessment
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {shown ? (
            <LabelBadge label={shown} basis={r.correctedLabel ? null : r.basis} size="lg" />
          ) : (
            <span className="text-body text-ink-2">No label is available for this video.</span>
          )}
          <Provenance r={r} />
          <ReviewStatusTag status={r.reviewStatus} />
        </div>
        {shown && (
          <p className="text-small text-ink-2">
            {labelDisplay(shown, r.correctedLabel ? null : r.basis).description}.{ruleLine ? ` ${ruleLine}` : ""}
          </p>
        )}
        {r.explanation && <p className="max-w-[72ch] font-serif text-[18px] leading-[30px] text-ink">{r.explanation}</p>}
      </div>

      {r.decidingClaims.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-cap font-semibold uppercase tracking-wider text-ink-3">How it was reached</h3>
          <ol className="flex flex-col gap-2">
            {r.decidingClaims.map((c) => (
              <Chain key={c.id} claim={c} r={r} />
            ))}
          </ol>
        </div>
      )}

      <dl className="grid gap-x-8 gap-y-1 text-small sm:grid-cols-[auto_1fr]">
        <dt className="font-semibold text-ink">Model confidence</dt>
        {/* Never a raw number until calibration exists (HANDOFF §6.5). */}
        <dd className="text-ink-2">Not yet calibrated. The label rests on the evidence below, not on a score.</dd>
      </dl>
    </section>
  );
}
