"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { EmptyState, Icon, LabelBadge, SeverityTag, buttonClass } from "@/components/ui";
import { reasonCounts, sortQueue, type QueueItem } from "@/lib/api/review-adapter";

type Props = {
  items: QueueItem[];
  view: "open" | "decided";
  onViewChange: (v: "open" | "decided") => void;
  /** Link to an item's workspace. */
  hrefFor: (item: QueueItem) => string;
  updatedAt?: Date | null;
};

/** ReviewQueue.dc.html: priority, then oldest first. Priority orders the queue; it never changes a label (§12). */
export function ReviewQueue({ items, view, onViewChange, hrefFor, updatedAt }: Props) {
  const [reason, setReason] = useState<string | null>(null);
  const sorted = useMemo(() => sortQueue(items), [items]);
  const counts = useMemo(() => reasonCounts(sorted), [sorted]);
  const shown = reason ? sorted.filter((i) => i.reasons.some((r) => r.rule === reason)) : sorted;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-h1 text-ink">Review queue</h1>
          <p className="text-small text-ink-2">High priority first, then the oldest. Priority only sets the order; it never changes a label.</p>
        </div>
        <div role="group" aria-label="Which cases" className="inline-flex rounded-md border border-line-input">
          {(["open", "decided"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => onViewChange(v)}
              className={`min-h-10 px-3 text-small font-semibold first:rounded-l-md last:rounded-r-md ${view === v ? "bg-ink text-bg" : "bg-surface text-ink-2"}`}
            >
              {v === "open" ? "Needs decision" : "Decided"}
            </button>
          ))}
        </div>
      </div>

      {counts.length > 0 && (
        <div role="group" aria-label="Filter by reason" className="flex flex-wrap gap-2">
          <button type="button" aria-pressed={reason === null} onClick={() => setReason(null)} className={chip(reason === null)}>
            All <span className="tabular-nums">{sorted.length}</span>
          </button>
          {counts.map((c) => (
            <button key={c.rule} type="button" aria-pressed={reason === c.rule} onClick={() => setReason(reason === c.rule ? null : c.rule)} className={chip(reason === c.rule)}>
              {c.text.replace(/\.$/, "")} <span className="tabular-nums">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState icon="inbox" title={view === "open" ? "Nothing to review" : "No decided cases yet"}>
          {view === "open" ? "New cases appear here when the system sends a video for review." : "Cases you and other reviewers decide appear here."}
        </EmptyState>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface shadow-1">
          <table className="w-full min-w-[880px] border-collapse text-small">
            <caption className="sr-only">Review cases, sorted by priority then waiting time</caption>
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                <th scope="col" className="px-4 py-2.5 font-semibold" aria-sort="descending">Priority</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Video</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Proposed label</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Why it needs review</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Waiting</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Submitted by</th>
                <th scope="col" className="px-4 py-2.5"><span className="sr-only">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.reviewId} className="border-b border-line align-top last:border-0 hover:bg-surface-2">
                  <td className="px-4 py-3">{i.severity ? <SeverityTag severity={i.severity} /> : <span className="text-ink-3">Not set</span>}</td>
                  <td className="px-4 py-3 font-mono text-ink">{i.filename}</td>
                  {i.withheld ? (
                    // T34: an open HIGH case shows the system's view only after the reviewer's own judgement.
                    <td colSpan={2} className="px-4 py-3 text-ink-2">
                      <span className="inline-flex items-center gap-1.5">
                        <Icon name="lock" className="!h-3.5 !w-3.5" />
                        Hidden until you record your own judgement
                      </span>
                    </td>
                  ) : (
                    <>
                      <td className="px-4 py-3">{i.proposedLabel ? <LabelBadge label={i.proposedLabel} /> : <span className="text-ink-3">None</span>}</td>
                      <td className="px-4 py-3">
                        <span className="text-ink">{i.reasons[0]?.text ?? "Flagged for a person to check."}</span>
                        {i.reasons.length > 1 && <span className="text-ink-3"> +{i.reasons.length - 1} more</span>}
                      </td>
                    </>
                  )}
                  <td className="px-4 py-3 text-right tabular-nums text-ink-2">{i.waiting}</td>
                  <td className="px-4 py-3 text-ink-2">{i.submittedBy ?? "Not recorded"}</td>
                  <td className="px-4 py-3 text-right">
                    {i.isOwn && i.open ? (
                      <span className="text-cap text-ink-3">Your submission. Another reviewer decides.</span>
                    ) : (
                      <Link href={hrefFor(i)} className={buttonClass(i.open ? "primary" : "secondary", "sm")}>
                        {i.open ? "Review" : "View"}
                        <span className="sr-only"> {i.filename}</span>
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="flex items-center gap-1.5 text-cap text-ink-3">
        <Icon name="info" className="!h-3.5 !w-3.5" />
        The queue refreshes every 30 seconds{updatedAt ? `; last updated ${updatedAt.toLocaleTimeString()}` : ""}.
      </p>
    </div>
  );
}

const chip = (on: boolean) =>
  `inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-small ${on ? "border-ink bg-ink text-bg" : "border-line-input bg-surface text-ink-2 hover:text-ink"}`;
