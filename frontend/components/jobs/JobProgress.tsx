"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, ErrorBanner, Icon, JobStateTag, WarnBanner, buttonClass } from "@/components/ui";
import { elapsed, failureText, type Progress, type StepStatus } from "@/lib/api/job-adapter";

type Props = {
  filename: string;
  jobId: string;
  errorCode: string | null;
  progress: Progress;
  lost: boolean;
  onCheckNow: () => void;
  onRetry?: () => Promise<void>;
};

const MARK: Record<StepStatus, { icon: string; cls: string; sr: string }> = {
  done: { icon: "checkc", cls: "text-nomisinfo-fg", sr: "done" },
  now: { icon: "loader", cls: "text-primary", sr: "in progress" },
  warn: { icon: "refresh", cls: "text-warn-fg", sr: "retrying" },
  fail: { icon: "xc", cls: "text-err-fg", sr: "failed here" },
  pending: { icon: "dashed", cls: "text-ink-3", sr: "not started" },
};

/** JobProgress.dc.html: stepper card plus "You can leave this page". No partial result is ever shown. */
export function JobProgress({ filename, jobId, errorCode, progress: p, lost, onCheckNow, onRetry }: Props) {
  // null until mounted: the server's clock and the browser's differ, so rendering the
  // timer during SSR would make React's hydration fail.
  const [now, setNow] = useState<number | null>(null);
  const [retrying, setRetrying] = useState(false);
  useEffect(() => {
    setNow(Date.now());
    if (p.finished) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [p.finished]);

  const failed = p.state === "FAILED";
  const headline = failed
    ? "The analysis didn't finish"
    : p.state === "QUEUED"
      ? "Waiting to start"
      : p.state === "RETRYING"
        ? "Temporary problem, retrying automatically"
        : "Analysing the video";

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-small text-ink-2">
        <Link href="/jobs" className="text-primary hover:underline">Videos</Link>
        <Icon name="chevr" className="!h-3.5 !w-3.5" />
        <span className="font-mono">{filename}</span>
      </nav>

      {lost && (
        <WarnBanner title="Lost connection." action={<Button variant="secondary" size="sm" onClick={onCheckNow}>Check now</Button>}>
          We&apos;ll keep trying. The analysis carries on without this page.
        </WarnBanner>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-labelledby="prog-h" className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6 shadow-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <JobStateTag status={p.state === "RETRYING" ? "RETRY_PENDING" : p.state ?? ""} />
            {!p.finished && p.startedAt && now !== null && <span className="font-mono text-small tabular-nums text-ink-2">{elapsed(p.startedAt, now)}</span>}
          </div>
          <h1 id="prog-h" className="font-serif text-h1 text-ink">{headline}</h1>
          <p className="text-body text-ink-2" aria-live="polite">
            {failed
              ? `${failureText(errorCode)}${p.failedStep ? ` It stopped at: ${p.failedStep}.` : ""}`
              : p.state === "QUEUED"
                ? "Your video is in the queue and will start shortly."
                : p.currentText
                  ? `Now: ${p.currentText}`
                  : "Finishing up…"}
          </p>

          {p.state === "RETRYING" && (
            <WarnBanner title="Temporary problem, retrying automatically.">
              {p.attempt > 1 ? `Attempt ${p.attempt}. ` : ""}Nothing for you to do.
            </WarnBanner>
          )}

          <ol className="flex flex-col">
            {p.steps.map((s, i) => {
              const m = MARK[s.status];
              return (
                <li key={s.key} className="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
                  <Icon name={m.icon} className={`!h-5 !w-5 ${m.cls}`} />
                  <span className={`flex-1 text-body ${s.status === "now" || s.status === "warn" ? "font-semibold text-ink" : s.status === "pending" ? "text-ink-3" : "text-ink"}`}>
                    <span className="sr-only">Step {i + 1}: </span>
                    {s.text}
                    <span className="sr-only">, {m.sr}</span>
                  </span>
                  {s.seconds !== null && <span className="font-mono text-cap tabular-nums text-ink-3">{s.seconds} s</span>}
                </li>
              );
            })}
          </ol>

          {failed && (
            <ErrorBanner
              title="No result was produced."
              action={
                <div className="flex flex-wrap gap-2">
                  {onRetry && (
                    <Button
                      size="sm"
                      disabled={retrying}
                      onClick={async () => {
                        setRetrying(true);
                        await onRetry();
                        setRetrying(false);
                      }}
                    >
                      {retrying ? "Starting…" : "Retry analysis"}
                    </Button>
                  )}
                  <Link href="/" className={buttonClass("secondary", "sm")}>Upload a different file</Link>
                </div>
              }
            >
              No partial result is shown. Job reference <span className="font-mono">{jobId}</span>
            </ErrorBanner>
          )}
        </section>

        {!p.finished && (
          <aside className="flex flex-col gap-2 rounded-lg border border-line bg-surface-2 p-5 text-small text-ink-2">
            <h2 className="text-h3 text-ink">You can leave this page</h2>
            <p>The analysis keeps running. Find it again under Videos; the result appears there when it&apos;s ready.</p>
            <p>Most videos take one to two minutes.</p>
          </aside>
        )}
      </div>
    </div>
  );
}
