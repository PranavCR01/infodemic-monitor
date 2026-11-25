import type { ClaimSearch as Search } from "@/lib/api/result-adapter";

const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;

/** "How we searched" for one claim (T31 search_trail), collapsed by default. */
export function ClaimSearch({ s }: { s: Search }) {
  return (
    <details className="border-t border-line pt-3">
      <summary className="cursor-pointer text-small font-semibold text-ink-2">How we searched for this claim</summary>
      <div className="mt-2 flex flex-col gap-2 text-small text-ink-2">
        <p>
          {s.retrieved !== null ? `${n(s.retrieved, "result", "results")} found, ` : ""}
          {s.screened} screened, {n(s.kept, "source", "sources")} used for the verdict.
        </p>
        {s.queries.length > 0 && (
          <div>
            <p className="font-semibold text-ink">PubMed searches</p>
            <ol className="mt-1 flex flex-col gap-1">
              {s.queries.map((q, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-2">
                  <code className="break-words rounded-sm bg-surface-sunken px-1.5 py-0.5 font-mono text-cap text-ink">{q.query}</code>
                  <span className="text-cap">
                    {q.failed ? "search failed" : q.results !== null ? n(q.results, "result", "results") : ""}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {s.sources.length > 0 && (
          <p>
            <span className="font-semibold text-ink">Official sources checked: </span>
            {s.sources.map((r) => r.name).join(", ")}
          </p>
        )}
        {s.libraryUsed && <p>The project&apos;s document library was searched too, because PubMed found little.</p>}
        {s.budgetExhausted && (
          <p>The search used all {s.roundsMax} rounds allowed for a claim, so a more specific study may exist that it didn&apos;t reach.</p>
        )}
        {s.partial && <p>This result is from an older run that recorded only the searches planned, not what each returned.</p>}
      </div>
    </details>
  );
}
