"use client";

import { useEffect, useRef, useState } from "react";
import { ReviewWorkspace } from "@/components/review/ReviewWorkspace";
import { ErrorBanner } from "@/components/ui";
import { fetchBlindMaterial, type BlindMaterial } from "@/lib/api/blind-material";
import { usePlaybackUrl } from "@/lib/api/playback";
import type { ResultModel } from "@/lib/api/result-adapter";
import type { CaseModel } from "@/lib/api/review-adapter";
import { fetchCase, fetchCaseEvidence, postDecision, postPreReveal, postSeverity } from "@/lib/api/reviews";
import { useViewerId } from "@/lib/hooks/useViewerId";

export function WorkspaceClient({ reviewId }: { reviewId: string }) {
  const [review, setReview] = useState<CaseModel | null>(null);
  const [result, setResult] = useState<ResultModel | null>(null);
  const [evidenceFailed, setEvidenceFailed] = useState(false);
  const [blindMaterial, setBlindMaterial] = useState<BlindMaterial | null>(null);
  const [blindMaterialFailed, setBlindMaterialFailed] = useState(false);
  const [reloads, setReloads] = useState(0);
  const reloadedForBlind = useRef(false);
  // T56: reviewers may play any case's video (ownership._row_visible); the server decides.
  const playback = usePlaybackUrl(review?.jobId ?? null);
  const [error, setError] = useState<string | null>(null);
  const viewerId = useViewerId();

  useEffect(() => {
    if (viewerId === undefined) return;
    let live = true;
    (async () => {
      const r = await fetchCase(reviewId, viewerId);
      if (!live) return;
      if (!r.ok) return setError(r.message);
      setReview(r.data);
    })();
    return () => {
      live = false;
    };
  }, [reviewId, viewerId, reloads]);

  // T40: while blind, the reviewer judges from the blind material (quotes and sources, no relations).
  const blindReviewId = review?.withheld ? review.reviewId : null;
  useEffect(() => {
    if (!blindReviewId) return;
    let live = true;
    (async () => {
      const m = await fetchBlindMaterial(blindReviewId);
      if (!live) return;
      if (m.kind === "ok") {
        setBlindMaterial(m.material);
        setBlindMaterialFailed(false);
      } else if (m.kind === "not_blind" && !reloadedForBlind.current) {
        // The server says this reviewer isn't blind any more (e.g. judged in another tab):
        // reload the case once. If the two still disagree, say the material couldn't load.
        reloadedForBlind.current = true;
        setReloads((n) => n + 1);
      } else {
        setBlindMaterialFailed(true);
      }
    })();
    return () => {
      live = false;
    };
  }, [blindReviewId]);

  // The evidence (the job's result) loads only once the system's view is revealed:
  // straight away on most cases, after the reviewer's own judgement on blind ones (T34).
  const jobId = review?.jobId;
  const withheld = review?.withheld ?? true;
  useEffect(() => {
    if (!jobId || withheld) return;
    let live = true;
    (async () => {
      const ev = await fetchCaseEvidence(jobId);
      if (!live) return;
      if (ev.kind === "ok") setResult(ev.result);
      // "blind" can't happen once revealed, unless the case changed under us: show no evidence.
      setEvidenceFailed(ev.kind === "error");
    })();
    return () => {
      live = false;
    };
  }, [jobId, withheld]);

  if (error) return <ErrorBanner title="This review couldn't be opened.">{error}</ErrorBanner>;
  if (!review) return <p className="text-small text-ink-2" aria-busy="true">Loading the case…</p>;
  return (
    <ReviewWorkspace
      review={review}
      result={result}
      evidenceFailed={evidenceFailed}
      blindMaterial={blindMaterial}
      blindMaterialFailed={blindMaterialFailed}
      videoUrl={playback.url}
      onVideoError={playback.onError}
      onDecide={(req) => postDecision(reviewId, req)}
      onPreReveal={async (body) => {
        // T34: the server records the judgement and answers with the revealed case.
        const r = await postPreReveal(reviewId, body, viewerId ?? null);
        if (!r.ok) return { ok: false, message: r.message };
        setReview(r.data);
        return { ok: true };
      }}
      onOverrideSeverity={(claimId, severity, reason) => postSeverity(reviewId, claimId, severity, reason)}
    />
  );
}
