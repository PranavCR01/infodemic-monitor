"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, EmptyState, Icon, JobStateTag, LabelBadge, buttonClass } from "@/components/ui";
import type { JobRow } from "@/lib/api/job-adapter";
import { EMPTY_FILTERS, PAGE_SIZE, type JobFilters } from "@/lib/job-filters";
import { JOB_STATES, LABELS, VIDEO_LABELS, type JobState } from "@/lib/vocabulary";


type Props = {
  rows: JobRow[] | null;
  total: number | null;
  filters: JobFilters;
  onFilters: (f: JobFilters) => void;
  error: string | null;
};

const hasFilters = (f: JobFilters) => Boolean(f.q || f.state || f.label || f.needsReview || f.mine);

/** Jobs.dc.html. Whole rows link to the video; filters live in the URL (the page). */
export function JobsList({ rows, total, filters: f, onFilters, error }: Props) {
  const [q, setQ] = useState(f.q);
  useEffect(() => setQ(f.q), [f.q]);
  const running = rows?.filter((r) => r.active).length ?? 0;
  const pages = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;
  // T33: reviewers and admins also see other people's videos. Show who submitted each
  // one, and offer "only mine", once a row from someone else appears (or the filter is on).
  const [seesOthers, setSeesOthers] = useState(false);
  useEffect(() => {
    if (rows?.some((r) => !r.isOwn && r.submittedBy !== null)) setSeesOthers(true);
  }, [rows]);
  const shared = seesOthers || f.mine;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-h1 text-ink">{shared && !f.mine ? "Videos" : "Your videos"}</h1>
          {running > 0 && <p className="text-small text-ink-2" aria-live="polite">Updating {running} running {running === 1 ? "job" : "jobs"}…</p>}
        </div>
        <Link href="/" className={buttonClass("primary")}>
          <Icon name="upload" /> Submit a video
        </Link>
      </div>

      <form
        role="search"
        className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3"
        onSubmit={(e) => {
          e.preventDefault();
          onFilters({ ...f, q: q.trim(), page: 1 });
        }}
      >
        <div className="flex min-w-[220px] flex-1 flex-col gap-1">
          <label htmlFor="jobs-q" className="text-small font-semibold text-ink">Search</label>
          <input id="jobs-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="File name or job reference" className="min-h-10 rounded-md border border-line-input bg-surface px-3 text-body" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="jobs-state" className="text-small font-semibold text-ink">State</label>
          <select id="jobs-state" value={f.state} onChange={(e) => onFilters({ ...f, state: e.target.value as JobState | "", page: 1 })} className="min-h-10 rounded-md border border-line-input bg-surface px-3 text-body">
            <option value="">Any state</option>
            {(Object.keys(JOB_STATES) as JobState[]).map((s) => (
              <option key={s} value={s}>{JOB_STATES[s].display}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="jobs-label" className="text-small font-semibold text-ink">Label</label>
          <select id="jobs-label" value={f.label} onChange={(e) => onFilters({ ...f, label: e.target.value, page: 1 })} className="min-h-10 rounded-md border border-line-input bg-surface px-3 text-body">
            <option value="">Any label</option>
            {VIDEO_LABELS.map((l) => (
              <option key={l} value={l}>{LABELS[l].display}</option>
            ))}
          </select>
        </div>
        <label className="flex min-h-10 items-center gap-2 text-small text-ink">
          <input type="checkbox" checked={f.needsReview} onChange={(e) => onFilters({ ...f, needsReview: e.target.checked, page: 1 })} />
          Needs review only
        </label>
        {shared && (
          <label className="flex min-h-10 items-center gap-2 text-small text-ink">
            <input type="checkbox" checked={f.mine} onChange={(e) => onFilters({ ...f, mine: e.target.checked, page: 1 })} />
            Only videos I submitted
          </label>
        )}
        <Button type="submit" variant="secondary">Search</Button>
      </form>

      {error && <p role="alert" className="rounded-md border border-err-bd bg-err-bg px-3 py-2 text-small text-err-fg">{error}</p>}

      {rows === null ? (
        <div aria-busy="true" aria-label="Loading your videos" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-md bg-surface-sunken motion-reduce:animate-none" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        hasFilters(f) ? (
          <EmptyState icon="search" title="No videos match" action={<Button variant="secondary" size="sm" onClick={() => onFilters(EMPTY_FILTERS)}>Clear filters</Button>}>
            Try a different search or fewer filters.
          </EmptyState>
        ) : (
          <EmptyState icon="upload" title="No videos yet" action={<Link href="/" className={buttonClass("primary", "sm")}>Submit your first video</Link>}>
            Videos you submit appear here with their progress and result.
          </EmptyState>
        )
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface shadow-1">
          <table className="w-full min-w-[720px] border-collapse text-small">
            <caption className="sr-only">{shared && !f.mine ? "Videos" : "Your videos"}, newest first</caption>
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                <th scope="col" className="px-4 py-2.5 font-semibold">Video</th>
                <th scope="col" className="px-4 py-2.5 font-semibold" aria-sort="descending">Submitted</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">State</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Label</th>
                {shared && <th scope="col" className="px-4 py-2.5 font-semibold">Submitted by</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.jobId} className="relative border-b border-line last:border-0 hover:bg-surface-2">
                  <td className="px-4 py-3">
                    {/* The link covers the row (::after), so the whole row is clickable with one tab stop. */}
                    <Link href={`/jobs/${r.jobId}`} className="font-mono text-ink after:absolute after:inset-0 after:content-[''] hover:underline">
                      {r.filename}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-ink-2">{r.submittedAt ? new Date(r.submittedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : ""}</td>
                  <td className="px-4 py-3">
                    <JobStateTag status={r.rawStatus} />
                    {r.step && <div className="text-cap text-ink-3">{r.step}</div>}
                  </td>
                  <td className="px-4 py-3">{r.label ? <LabelBadge label={r.label} basis={r.basis} /> : <span className="text-ink-3">Not yet</span>}</td>
                  {shared && <td className="px-4 py-3 text-ink-2">{r.submittedBy ?? <span className="text-ink-3">Not recorded</span>}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages !== null && pages > 1 && (
        <nav aria-label="Pages" className="flex items-center justify-end gap-2 text-small">
          <Button variant="secondary" size="sm" disabled={f.page <= 1} onClick={() => onFilters({ ...f, page: f.page - 1 })}>Previous</Button>
          <span className="text-ink-2">Page {f.page} of {pages}</span>
          <Button variant="secondary" size="sm" disabled={f.page >= pages} onClick={() => onFilters({ ...f, page: f.page + 1 })}>Next</Button>
        </nav>
      )}
    </div>
  );
}
