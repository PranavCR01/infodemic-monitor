"use client";

import { useEffect, useMemo, useState } from "react";
import { ResultView } from "@/components/result/ResultView";
import { EmptyState, ErrorBanner, JobStateTag } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { adaptResult } from "@/lib/api/result-adapter";
import type { RawResult } from "@/lib/api/result-types";
import { toJobState } from "@/lib/vocabulary";

type Job = {
  job_id: string;
  status: string;
  error_code: string | null;
  created_at: string;
};

// Plain-language failure reasons. The progress view (chunk 6) replaces this with
// the step the job failed at (T28).
const ERROR_MESSAGES: Record<string, string> = {
  STORAGE_ERROR: "We couldn't read the video file.",
  TRANSCRIPTION_ERROR: "We couldn't transcribe the speech in the video.",
  INFERENCE_ERROR: "The analysis stopped before it finished.",
  GROUNDING_ERROR: "The evidence search stopped before it finished.",
};
const UNKNOWN_ERROR = "The analysis stopped because of an unexpected problem.";

export function JobDetailClient({
  jobId,
  initialJob,
  initialResult,
}: {
  jobId: string;
  initialJob: Job;
  initialResult: RawResult | null;
}) {
  const [job, setJob] = useState<Job>(initialJob);
  const [raw, setRaw] = useState<RawResult | null>(initialResult);
  const state = toJobState(job.status);
  const active = state === "QUEUED" || state === "RUNNING" || state === "RETRYING";
  const finished = state === "COMPLETED" || state === "NEEDS_REVIEW";

  // Interim polling; chunk 6 replaces it with the shared polling hook (HANDOFF §6.4).
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(async () => {
      try {
        const jobRes = await apiFetch(`/jobs/${jobId}`);
        if (!jobRes.ok) return;
        const updated: Job = await jobRes.json();
        setJob(updated);
        const s = toJobState(updated.status);
        if (s === "COMPLETED" || s === "NEEDS_REVIEW") {
          const resultRes = await apiFetch(`/jobs/${jobId}/result`);
          if (resultRes.status === 200) setRaw(await resultRes.json());
        }
      } catch {
        // a missed poll is retried on the next tick
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [active, jobId]);

  const result = useMemo(() => (raw ? adaptResult(raw) : null), [raw]);

  if (finished && result) return <ResultView result={result} />;

  if (state === "FAILED") {
    return (
      <div className="mx-auto max-w-2xl py-8">
        <ErrorBanner title="The analysis didn't finish.">
          <p>{(job.error_code && ERROR_MESSAGES[job.error_code]) || UNKNOWN_ERROR} No partial result is shown.</p>
          <p className="mt-1 text-cap text-ink-3">
            Job reference <span className="font-mono">{job.job_id}</span>
          </p>
        </ErrorBanner>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl py-8">
      <EmptyState icon="loader" title={finished ? "Loading the result…" : "Analysis in progress"}>
        <span className="flex flex-col items-center gap-2">
          <JobStateTag status={job.status} />
          <span aria-live="polite">You can leave this page; the result will be here when it&apos;s ready.</span>
        </span>
      </EmptyState>
    </div>
  );
}
