"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon, ReviewBanner, ReviewReasonChip, buttonClass } from "@/components/ui";
import { claimAt, type Claim, type ResultModel } from "@/lib/api/result-adapter";
import type { RequestOutcome } from "@/lib/api/review-request";
import { Assessment } from "./Assessment";
import { ClaimDrawer } from "./ClaimDrawer";
import { ClaimCard } from "./ClaimCard";
import { ClaimTimeline } from "./ClaimTimeline";
import { HowWeSearched } from "./HowWeSearched";
import { Transcript } from "./Transcript";

type Props = {
  result: ResultModel;
  /** Signed playback URL (T29). Without it the page works, minus the player. */
  videoUrl?: string | null;
  /** Called when the player fails to load, e.g. an expired URL (fetches a fresh one). */
  onVideoError?: () => void;
  /** T32: ask for a person to check a result the review rule didn't send to review. */
  onRequestReview?: (note: string) => Promise<RequestOutcome>;
};

/**
 * Video result, two-column version (Q5: Direction 3's margin notes come last).
 * One `activeId` is shared by the timeline, the transcript and the claim cards.
 */
export function ResultView({ result: r, videoUrl = null, onVideoError, onRequestReview }: Props) {
  const [activeId, setActiveId] = useState<string | null>(r.decidingClaims[0]?.id ?? r.claims[0]?.id ?? null);
  const videoRef = useRef<HTMLVideoElement>(null);
  // The open claim lives in the URL (?claim=c2), so a claim can be linked to.
  // history.replaceState keeps Next's useSearchParams in sync without a server round trip.
  const params = useSearchParams();
  const fromUrl = params?.get("claim") ?? null;
  const valid = useCallback((id: string | null) => (id && r.claims.some((c) => c.id === id) ? id : null), [r.claims]);
  const [openId, setOpenId] = useState<string | null>(() => valid(fromUrl));
  useEffect(() => setOpenId(valid(fromUrl)), [fromUrl, valid]);
  const setOpen = useCallback((id: string | null) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("claim", id);
    else url.searchParams.delete("claim");
    window.history.replaceState(window.history.state, "", url);
    setOpenId(id);
    if (id) setActiveId(id);
  }, []);
  const cardRefs = useRef(new Map<string, HTMLElement>());

  const select = useCallback((c: Claim, scroll = true) => {
    setActiveId(c.id);
    if (scroll) {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      cardRefs.current.get(c.id)?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    }
  }, []);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = t;
      void v.play().catch(() => {});
    }
    const c = claimAt(r.claims, t);
    if (c) setActiveId(c.id);
  }, [r.claims]);

  // Playback selects the claim being spoken, at most 4 times a second.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    let last = 0;
    const onTime = () => {
      const now = performance.now();
      if (now - last < 250) return;
      last = now;
      const c = claimAt(r.claims, v.currentTime);
      if (c) setActiveId(c.id);
    };
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [r.claims, videoUrl]);

  const duration = Math.max(0, ...r.transcript.map((s) => s.end), ...r.claims.map((c) => c.end));

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-small text-ink-2">
        <Link href="/jobs" className="text-primary hover:underline">
          Videos
        </Link>
        <Icon name="chevr" className="!h-3.5 !w-3.5" />
        <span className="font-mono">{r.filename}</span>
      </nav>

      {r.reviewStatus === "PENDING" && (
        <ReviewBanner>
          {r.reasons.length > 0
            ? r.reasons.map((reason, i) => (
                <ReviewReasonChip key={i} code={reason.code} text={reason.claimNumber ? `Claim ${reason.claimNumber}: ${reason.text}` : reason.text} />
              ))
            : null}
        </ReviewBanner>
      )}

      <Assessment r={r} onRequestReview={onRequestReview} />

      {!r.hasClaimLevel ? (
        <section className="rounded-lg border border-line bg-surface p-6 text-small text-ink-2 shadow-1">
          This result was produced without claim-by-claim checking, so there are no claims, quotes or sources to show.
        </section>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(380px,460px)]">
          <section aria-labelledby="transcript-h" className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-4 shadow-1 lg:sticky lg:top-4">
            {videoUrl ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption -- the transcript below is the text alternative
              <video ref={videoRef} src={videoUrl} controls preload="metadata" onError={onVideoError} className="max-h-[360px] w-full rounded-md bg-black" />
            ) : (
              <p className="flex items-center gap-2 rounded-md bg-surface-sunken px-3 py-2 text-small text-ink-2">
                <Icon name="play" /> Video playback isn&apos;t available for this video. The transcript and claims are complete.
              </p>
            )}
            <ClaimTimeline claims={r.claims} duration={duration} activeId={activeId} onSelect={(c) => { select(c); seek(c.start); }} />
            <h2 id="transcript-h" className="text-h2 text-ink">
              Transcript and on-screen text
            </h2>
            <div className="max-h-[60vh] overflow-y-auto">
              <Transcript segments={r.transcript} claims={r.claims} activeId={activeId} onSeek={seek} onSelect={(c) => select(c)} />
            </div>
          </section>

          <section aria-labelledby="claims-h" className="flex flex-col gap-3">
            <h2 id="claims-h" className="text-h2 text-ink">
              Claims ({r.claims.length})
            </h2>
            {r.claims.map((c) => (
              <ClaimCard
                key={c.id}
                ref={(el) => {
                  if (el) cardRefs.current.set(c.id, el);
                  else cardRefs.current.delete(c.id);
                }}
                claim={c}
                active={c.id === activeId}
                onSelect={() => select(c, false)}
                onSeek={seek}
                onOpen={() => setOpen(c.id)}
              />
            ))}
          </section>
        </div>
      )}

      {r.search && <HowWeSearched search={r.search} />}

      <ClaimDrawer
        claims={r.claims}
        openId={openId}
        transcript={r.transcript}
        onNavigate={(id) => setOpen(id)}
        onClose={() => setOpen(null)}
        onPlay={seek}
      />

      <p className="text-cap text-ink-3">
        <Link href="/jobs" className={buttonClass("ghost", "sm")}>
          Back to your videos
        </Link>
      </p>
    </div>
  );
}
