import { JOB_STATES, REVIEW_STATUS, SEVERITY, toJobState, type ReviewStatus, type Severity } from "@/lib/vocabulary";
import { Icon } from "./Icon";

// Statuses are text + icon with no fill, so they don't compete with the label.

export function ReviewStatusTag({ status }: { status: ReviewStatus }) {
  const m = REVIEW_STATUS[status];
  const tone = status === "PENDING" ? "text-warn-fg" : "text-ink-2";
  return (
    <span data-review-status={status} className={`inline-flex items-center gap-1.5 text-small font-medium ${tone}`}>
      <Icon name={m.icon} className="!h-3.5 !w-3.5" />
      {m.display}
    </span>
  );
}

/** Accepts the backend's raw status (today's or T28's); never prints an unknown value. */
export function JobStateTag({ status }: { status: string | null | undefined }) {
  const state = toJobState(status);
  if (!state) {
    return <span className="text-small font-medium text-ink-3">Unknown state</span>;
  }
  const m = JOB_STATES[state];
  const tone = state === "FAILED" ? "text-err-fg" : state === "RETRYING" || state === "NEEDS_REVIEW" ? "text-warn-fg" : "text-ink-2";
  return (
    <span data-job-state={state} className={`inline-flex items-center gap-1.5 text-small font-medium ${tone}`}>
      <Icon name={m.icon} className="!h-3.5 !w-3.5" />
      {m.display}
    </span>
  );
}

/** Review priority (§12). Orders the queue; never shown as a judgement on the video. */
export function SeverityTag({ severity }: { severity: Severity }) {
  const m = SEVERITY[severity];
  return (
    <span data-severity={severity} className={`inline-flex items-center gap-1.5 text-small ${severity === "HIGH" ? "font-semibold text-ink" : "text-ink-2"}`}>
      <Icon name={m.icon} className="!h-3.5 !w-3.5" />
      {m.display}
    </span>
  );
}
