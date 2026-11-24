"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { JobProgress } from "@/components/jobs/JobProgress";
import { ResultView } from "@/components/result/ResultView";
import { apiFetch } from "@/lib/api";
import type { Progress } from "@/lib/api/job-adapter";
import type { RawJob } from "@/lib/api/job-types";
import { fetchProgress, retryJob } from "@/lib/api/jobs";
import { adaptResult } from "@/lib/api/result-adapter";
import type { RawResult } from "@/lib/api/result-types";
import { usePolling } from "@/lib/hooks/usePolling";
import { toJobState } from "@/lib/vocabulary";

type Props = { jobId: string; initialJob: RawJob; initialResult: RawResult | null; filename?: string | null };

/** HANDOFF §5: /jobs/[id] shows progress until the job is finished, then the result. */
export function JobDetailClient({ jobId, initialJob, initialResult, filename }: Props) {
  const router = useRouter();
  const [job, setJob] = useState<RawJob>(initialJob);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [raw, setRaw] = useState<RawResult | null>(initialResult);

  const state = toJobState(job.state ?? job.status);
  const hasResult = (state === "COMPLETED" || state === "NEEDS_REVIEW") && raw !== null;
  const stop = hasResult || state === "FAILED";

  const poll = useCallback(async () => {
    const r = await fetchProgress(jobId);
    if (!r) return false;
    setProgress(r.progress);
    if (r.job) setJob(r.job);
    const s = toJobState(r.job?.state ?? r.job?.status ?? r.progress.state);
    if (s === "COMPLETED" || s === "NEEDS_REVIEW") {
      const res = await apiFetch(`/jobs/${encodeURIComponent(jobId)}/result`);
      if (res.status === 200) setRaw(await res.json());
    }
    return true;
  }, [jobId]);
  const { lost, checkNow } = usePolling(poll, stop);

  const result = useMemo(() => (raw ? adaptResult(raw) : null), [raw]);
  if (hasResult && result) return <ResultView result={result} />;

  const shown: Progress =
    progress ?? {
      state, steps: [], currentText: null, attempt: job.attempts ?? 0, finished: state === "FAILED", startedAt: job.created_at ?? null, failedStep: null,
    };
  return (
    <JobProgress
      filename={filename ?? result?.filename ?? "Your video"}
      jobId={job.job_id}
      errorCode={job.error_code ?? null}
      progress={shown}
      lost={lost}
      onCheckNow={() => void checkNow()}
      onRetry={async () => {
        const next = await retryJob(job.video_id);
        if (next) router.push(`/jobs/${next}`);
      }}
    />
  );
}
