import type { ResultModel } from "@/lib/api/result-adapter";

/** All claims' searches together (T31); each claim's own trail is in its drawer. */
export function HowWeSearched({ search }: { search: NonNullable<ResultModel["search"]> }) {
  return (
    <details className="rounded-lg border border-line bg-surface p-4 shadow-1">
      <summary className="cursor-pointer text-h3 text-ink">How we searched</summary>
      <dl className="mt-3 grid gap-x-6 gap-y-2 text-small sm:grid-cols-[auto_1fr]">
        {search.queries.length > 0 && (
          <>
            <dt className="font-semibold text-ink">PubMed searches</dt>
            <dd className="flex flex-col gap-1">
              {search.queries.map((q) => (
                <code key={q} className="break-words rounded-sm bg-surface-sunken px-1.5 py-0.5 font-mono text-cap text-ink">
                  {q}
                </code>
              ))}
            </dd>
          </>
        )}
        {search.sites.length > 0 && (
          <>
            <dt className="font-semibold text-ink">Official sources checked</dt>
            <dd className="text-ink-2">{search.sites.join(", ")}</dd>
          </>
        )}
        {search.screened !== null && (
          <>
            <dt className="font-semibold text-ink">Results</dt>
            <dd className="text-ink-2">
              {search.screened} screened{search.kept !== null ? `, ${search.kept} used for the verdicts` : ""}
            </dd>
          </>
        )}
        {search.ranAt && (
          <>
            <dt className="font-semibold text-ink">Run</dt>
            <dd className="text-ink-2">{new Date(search.ranAt).toLocaleString()}</dd>
          </>
        )}
      </dl>
    </details>
  );
}
