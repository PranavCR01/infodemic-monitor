import type { Claim } from "@/lib/api/result-adapter";
import { searchFinding, unusedSources } from "@/lib/search-finding";

const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;

type Props = {
  claim: Pick<Claim, "id" | "search" | "sources" | "criticNotes" | "verdict">;
  /** A review reason names this claim. */
  sentToReviewer: boolean;
  /** Review screen only: the raw critic notes and every query, behind a toggle (T52). */
  technical?: boolean;
};

/**
 * "How we searched" for one claim (T31 trail, T52 wording): one plain-language finding.
 * The papers retrieved but not used are listed with the sources (T59). The critic's
 * pipeline notes and the raw queries are never shown on the result page.
 */
export function ClaimSearch({ claim: c, sentToReviewer, technical = false }: Props) {
  const s = c.search;
  if (!s) return null;
  const finding = searchFinding(c, sentToReviewer);
  // T59: papers retrieved but not used are listed with the sources ("Also retrieved, not used").
  const unused = unusedSources(c);
  const droppedUnlisted = unused.length === 0 && s.kept === 0 && (s.retrieved ?? s.screened) > 0;

  return (
    <section aria-labelledby={`search-${c.id}`} className="flex flex-col gap-2 border-t border-line pt-3 text-small text-ink-2">
      <h4 id={`search-${c.id}`} className="text-cap font-semibold uppercase tracking-wider text-ink-3">How we searched</h4>
      {finding && <p className="text-ink">{finding}</p>}
      {s.sources.length > 0 && (
        <p>
          <span className="font-semibold text-ink">Official sources checked: </span>
          {s.sources.map((r) => r.name).join(", ")}
        </p>
      )}
      {s.libraryUsed && <p>The project&apos;s document library was searched too, because PubMed found little.</p>}

      {droppedUnlisted && (
        <p className="text-cap text-ink-3">The titles of the papers that weren&apos;t relevant enough to check weren&apos;t kept.</p>
      )}

      {technical && (
        <details className="rounded-md border border-line px-3 py-2">
          <summary className="cursor-pointer font-semibold text-ink-2">Technical details</summary>
          <div className="mt-2 flex flex-col gap-2">
            {s.rounds.length > 0 && (
              <div>
                <p className="font-semibold text-ink">PubMed queries, as run</p>
                <ol className="mt-1 flex flex-col gap-1">
                  {s.rounds.map((q, i) => (
                    <li key={i} className="flex flex-wrap items-baseline gap-2">
                      <span className="text-cap tabular-nums text-ink-3">Round {q.round}</span>
                      <code className="break-words rounded-sm bg-surface-sunken px-1.5 py-0.5 font-mono text-cap text-ink">{q.query}</code>
                      <span className="text-cap">
                        {q.failed ? "search failed" : q.results !== null ? n(q.results, "result", "results") : ""}
                        {q.repeat ? " · repeated, not counted again" : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <p>
              {s.retrieved !== null ? `${n(s.retrieved, "result", "results")} returned, ` : ""}
              {s.screened} screened, {s.kept} passed to the check. Rounds used: {s.roundsUsed} of {s.roundsMax}.
            </p>
            {s.partial && <p>This older analysis recorded only the queries planned, not what each returned.</p>}
            {c.criticNotes.length > 0 && (
              <div>
                <p className="font-semibold text-ink">Notes from the second automated check</p>
                <ul className="mt-1 list-disc pl-5">
                  {c.criticNotes.map((note, k) => (
                    <li key={k}>{note}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}
    </section>
  );
}
