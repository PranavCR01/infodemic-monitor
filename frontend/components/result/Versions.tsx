import Link from "next/link";
import { Icon, LabelBadge } from "@/components/ui";
import type { ResultModel } from "@/lib/api/result-adapter";

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * T55: where this result sits among the video's analyses. A notice when a newer run is
 * going or failed, or when this is an older version; then "Previous analyses", newest first.
 */
export function VersionNotices({ r }: { r: ResultModel }) {
  const v = r.versions;
  return (
    <>
      {!v.isCurrent && v.currentJobId && (
        <p role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-warn-bd bg-warn-bg px-4 py-3 text-small text-warn-fg">
          <Icon name="clock" className="!h-4 !w-4" />
          This is an older analysis of this video.
          <Link href={`/jobs/${encodeURIComponent(v.currentJobId)}`} className="font-semibold underline">
            See the current result
          </Link>
        </p>
      )}
      {v.latest?.running && (
        <p role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 px-4 py-3 text-small text-ink">
          <Icon name="loader" className="!h-4 !w-4" />
          A new analysis of this video is running. This result stays current until it finishes.
          <Link href={`/jobs/${encodeURIComponent(v.latest.jobId)}`} className="font-semibold text-primary underline">
            Follow its progress
          </Link>
        </p>
      )}
      {v.latest?.failed && (
        <p role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-err-bd bg-err-bg px-4 py-3 text-small text-err-fg">
          <Icon name="alert" className="!h-4 !w-4" />
          The latest re-analysis of this video didn&apos;t finish, so this result is still the current one.
          <Link href={`/jobs/${encodeURIComponent(v.latest.jobId)}`} className="font-semibold underline">
            See what happened
          </Link>
        </p>
      )}
    </>
  );
}

export function PreviousAnalyses({ r }: { r: ResultModel }) {
  const v = r.versions;
  if (v.previous.length === 0) return null;
  return (
    <section aria-labelledby="versions-h" className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-1">
      <h2 id="versions-h" className="text-h3 text-ink">Previous analyses</h2>
      <ol className="flex flex-col gap-2">
        <li className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-small">
          <span className="font-semibold text-ink">{v.isCurrent ? "This analysis" : "This analysis (older)"}</span>
          {v.isCurrent && <span className="rounded-sm bg-ink px-1.5 text-cap font-semibold text-bg">Current</span>}
          {r.label && <LabelBadge label={r.correctedLabel ?? r.label} basis={r.correctedLabel ? null : r.basis} />}
          {r.analysisVersion && <code className="font-mono text-cap text-ink-3">{r.analysisVersion}</code>}
        </li>
        {v.previous.map((p) => (
          <li key={p.jobId} className="flex flex-wrap items-center gap-2 rounded-md border border-line px-3 py-2 text-small">
            {p.rejected ? (
              <span className="text-ink-2">{when(p.finishedAt) || "Earlier analysis"} · rejected by a reviewer</span>
            ) : (
              <Link href={`/jobs/${encodeURIComponent(p.jobId)}`} className="text-primary underline">
                {when(p.finishedAt) || "Earlier analysis"}
              </Link>
            )}
            {p.jobId === v.currentJobId && <span className="rounded-sm bg-ink px-1.5 text-cap font-semibold text-bg">Current</span>}
            {p.label && <LabelBadge label={p.label} basis={p.basis} />}
            {p.pipelineVersion && <code className="font-mono text-cap text-ink-3">{p.pipelineVersion}</code>}
          </li>
        ))}
      </ol>
    </section>
  );
}
