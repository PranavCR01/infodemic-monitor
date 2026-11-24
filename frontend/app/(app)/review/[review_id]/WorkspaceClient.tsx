"use client";

import { useEffect, useState } from "react";
import { ReviewWorkspace } from "@/components/review/ReviewWorkspace";
import { ErrorBanner } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { adaptResult, type ResultModel } from "@/lib/api/result-adapter";
import type { CaseModel } from "@/lib/api/review-adapter";
import { fetchCase, postDecision, postSeverity } from "@/lib/api/reviews";

export function WorkspaceClient({ reviewId }: { reviewId: string }) {
  const [review, setReview] = useState<CaseModel | null>(null);
  const [result, setResult] = useState<ResultModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      const r = await fetchCase(reviewId);
      if (!live) return;
      if (!r.ok) return setError(r.message);
      setReview(r.data);
      try {
        const res = await apiFetch(`/jobs/${encodeURIComponent(r.data.jobId)}/result`);
        if (live && res.status === 200) setResult(adaptResult(await res.json()));
      } catch {
        // the workspace says the evidence couldn't be loaded
      }
    })();
    return () => {
      live = false;
    };
  }, [reviewId]);

  if (error) return <ErrorBanner title="This review couldn't be opened.">{error}</ErrorBanner>;
  if (!review) return <p className="text-small text-ink-2" aria-busy="true">Loading the case…</p>;
  return (
    <ReviewWorkspace
      review={review}
      result={result}
      onDecide={(req) => postDecision(reviewId, req)}
      onOverrideSeverity={(claimId, severity, reason) => postSeverity(reviewId, claimId, severity, reason)}
    />
  );
}
