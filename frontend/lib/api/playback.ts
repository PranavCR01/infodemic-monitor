"use client";

// T29 (#80): GET /v1/jobs/{job_id}/playback → a short-lived signed URL for the video.
// The URL is a credential: never stored or logged here, only held in state.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

export type Playback = { url: string; expiresAt: number };

export async function fetchPlayback(jobId: string): Promise<Playback | null> {
  try {
    const res = await apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}/playback`, { cache: "no-store" });
    // 404 no stored video (legacy upload), 501 local storage, 503 storage down: no player.
    if (!res.ok) return null;
    const body = (await res.json()) as { url?: string; expires_at?: string };
    const expiresAt = body.expires_at ? Date.parse(body.expires_at) : NaN;
    return body.url && Number.isFinite(expiresAt) ? { url: body.url, expiresAt } : null;
  } catch {
    return null;
  }
}

/** Refresh this long before the URL expires, so playback and seeking keep working. */
export const REFRESH_BEFORE_MS = 60_000;

export function refreshDelay(expiresAt: number, now = Date.now()): number {
  return Math.max(5_000, expiresAt - now - REFRESH_BEFORE_MS);
}

/**
 * The signed URL for a job's video, renewed before it expires. `onError` (wire it to
 * the <video> element's error event) fetches a fresh URL once, for a URL that expired
 * while the tab was asleep. Returns null when there is no playable video.
 */
export function usePlaybackUrl(jobId: string | null) {
  const [playback, setPlayback] = useState<Playback | null>(null);
  const retried = useRef(false);

  const load = useCallback(async () => {
    if (!jobId) return;
    setPlayback(await fetchPlayback(jobId));
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!playback) return;
    const t = setTimeout(() => void load(), refreshDelay(playback.expiresAt));
    return () => clearTimeout(t);
  }, [playback, load]);

  const onError = useCallback(() => {
    if (retried.current) return;
    retried.current = true;
    void load();
  }, [load]);

  return { url: playback?.url ?? null, onError };
}
