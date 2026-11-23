import { clock, evidenceText, type ResultModel } from "@/lib/api/result-adapter";
import { sortSources } from "@/components/result/SourceCard";
import { LabelBadge } from "@/components/ui";
import {
  claimMeaning,
  DECISION_RULE_TEXT,
  EVIDENCE_LEVEL_DISPLAY,
  labelDisplay,
  REVIEW_STATUS,
  STANCES,
  studyTypeDisplay,
  VERDICTS,
} from "@/lib/vocabulary";

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC" : "Not recorded";

const MODALITY = { speech: "speech", screen: "on-screen text only", both: "speech and on-screen text" } as const;

/**
 * Export / print view (Export.dc.html). Built from the result already returned by
 * the API, so it needs no export endpoint. Rules (HANDOFF §6.10):
 * - the label is never printed without its one-sentence rationale;
 * - a REJECTED result prints no label at all;
 * - every label, verdict and stance is printed as words, so the page reads in greyscale;
 * - no model IDs (they only appear on the evaluation screen).
 */
export function ExportReport({ r, recordUrl }: { r: ResultModel; recordUrl: string }) {
  const rejected = r.reviewStatus === "REJECTED";
  const label = r.correctedLabel ?? r.label;
  const basis = r.correctedLabel ? null : r.basis;
  const human = r.reviewStatus === "VERIFIED" || r.reviewStatus === "CORRECTED";
  const reason = label === "CANNOT_RECOGNIZE" && r.decisionRule ? DECISION_RULE_TEXT[r.decisionRule] : null;

  return (
    <article className="export mx-auto flex max-w-[7in] flex-col gap-5 bg-surface p-8 text-ink print:max-w-none print:p-0 print:text-[12pt]">
      <p className="flex justify-between border-b border-line pb-2 text-cap text-ink-2">
        <span>WHO Infodemic Monitor · Video assessment report</span>
        <span>{human ? `Analyst-confirmed (${REVIEW_STATUS[r.reviewStatus].display.toLowerCase()})` : "System assessment"}</span>
      </p>

      <h1 className="break-all font-mono text-h2">{r.filename}</h1>

      {rejected ? (
        <section className="rounded-md border border-line p-4">
          <p className="font-semibold">No label. A reviewer rejected this analysis.</p>
          <p className="text-small text-ink-2">The result could not be used (for example, the wrong video or unusable audio), so no label is reported.</p>
        </section>
      ) : label ? (
        <section className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <LabelBadge label={label} basis={basis} size="lg" />
            <span className="text-small font-semibold">{labelDisplay(label, basis).description}.</span>
          </div>
          {reason && <p className="text-small">{reason}</p>}
          <p className="font-serif text-[17px] leading-[27px]">{r.explanation}</p>
        </section>
      ) : (
        <p>No label is available for this video.</p>
      )}

      <table className="w-full border-collapse text-small">
        <tbody>
          {[
            ["Review status", r.reviewStatus === "PENDING" ? "Pending review. Treat the label as provisional." : REVIEW_STATUS[r.reviewStatus].display + (r.reviewDecidedAt ? `, ${fmt(r.reviewDecidedAt)}` : "")],
            ["Confidence", "Not yet calibrated"],
            ["Submitted", fmt(r.submittedAt)],
            ["Online record", recordUrl],
          ].map(([k, v]) => (
            <tr key={k} className="border-b border-line">
              <th scope="row" className="w-40 py-1.5 pr-4 text-left font-semibold">{k}</th>
              <td className="break-all py-1.5">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {r.hasClaimLevel && (
        <section className="flex flex-col gap-4">
          <h2 className="text-h2">Claims</h2>
          <p className="text-small text-ink-2">
            {r.claims.length} {r.claims.length === 1 ? "claim" : "claims"} found. ★ marks a claim that decided the label.
          </p>
          {r.claims.map((c) => {
            const sources = sortSources(c.sources);
            return (
              <div key={c.id} className="flex break-inside-avoid flex-col gap-1.5 border-t border-line pt-3">
                <h3 className="font-semibold">
                  {c.deciding ? "★ " : ""}
                  {c.number}. {c.text}
                </h3>
                <p className="text-small text-ink-2">
                  {clock(c.start)}–{clock(c.end)}
                  {c.modality ? ` · ${MODALITY[c.modality]}` : ""}
                </p>
                <p className="text-small">
                  <strong>{c.stance ? STANCES[c.stance].display : "Stance not assessed"}</strong>
                  {c.quotes[0] ? <> · The speaker says: <q>{c.quotes[0].text}</q></> : null}
                </p>
                <p className="text-small">
                  <strong>{c.verdict ? VERDICTS[c.verdict].display : "Not checked"}</strong> · {evidenceText(c.evidence, EVIDENCE_LEVEL_DISPLAY)}.
                </p>
                {c.verdictExplanation && <p className="text-small">{c.verdictExplanation}</p>}
                {c.stance && c.verdict && <p className="text-small italic">{claimMeaning(c.stance, c.verdict)}</p>}
                {c.limitations.length > 0 && <p className="text-small">Limitations: {c.limitations.join(" ")}</p>}
                {sources.length > 0 && (
                  <ol className="list-decimal pl-6 text-small">
                    {sources.map((s) => (
                      <li key={s.id}>
                        {s.title}. {[s.publisher, s.year].filter(Boolean).join(", ")}
                        {s.publisher || s.year ? ". " : ""}
                        {s.level === "GUIDANCE" ? "Official guidance" : studyTypeDisplay(s.studyType)}.{" "}
                        {s.relation === "SUPPORTS" ? "Supports." : s.relation === "CONTRADICTS" ? "Contradicts." : ""}{" "}
                        {s.kind === "library" ? "Internal library (cited by title only)." : s.pmid ? `PMID ${s.pmid}.` : s.url ?? ""}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            );
          })}
        </section>
      )}

      <section className="break-inside-avoid rounded-md border border-line p-4 text-small">
        <h2 className="mb-1 font-semibold">How this was checked</h2>
        <p>
          Speech and on-screen text were transcribed and split into health claims. Each claim was checked against PubMed
          research and official health sources{r.search?.sites.length ? ` (${r.search.sites.join(", ")})` : ""}.
          {r.search?.screened != null ? ` ${r.search.screened} results were screened and ${r.search.kept ?? 0} kept.` : ""}
          {" "}Uncertain or high-risk results go to a human reviewer.
        </p>
      </section>

      <section className="break-inside-avoid text-small">
        <h2 className="mb-1 font-semibold">How to read this report</h2>
        <p>
          Each verdict reflects what the cited sources show, not an opinion. INSUFFICIENT EVIDENCE means no source tests the
          claim: it is untested, not false. NO SUPPORTING EVIDENCE means a claimed remedy has no evidence behind it.
          DEBUNKED videos raise a false claim in order to correct it. CANNOT RECOGNIZE means the system declined to label
          the video.
        </p>
      </section>

      <p className="border-t border-line pt-2 text-cap text-ink-2">
        Produced with the Infodemic Monitor research tool for internal WHO research use. Internal library documents are cited by title only.
      </p>
    </article>
  );
}
