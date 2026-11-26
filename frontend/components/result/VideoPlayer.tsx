"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import { Icon } from "@/components/ui";

export type PlayerHandle = {
  /** Jump to a moment and play. Does nothing without a player. */
  seek: (seconds: number) => void;
  video: HTMLVideoElement | null;
};

type Props = {
  /** Signed playback URL (T29). Null: no playable video, so a short note is shown instead. */
  url: string | null;
  onError?: () => void;
  className?: string;
};

/** The job's video (result page and review screen). The transcript is its text alternative. */
export const VideoPlayer = forwardRef<PlayerHandle, Props>(function VideoPlayer({ url, onError, className = "" }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  useImperativeHandle(
    ref,
    () => ({
      seek(t: number) {
        const v = videoRef.current;
        if (!v) return;
        v.currentTime = t;
        void v.play()?.catch(() => {});
      },
      get video() {
        return videoRef.current;
      },
    }),
    [],
  );
  if (!url) {
    return (
      <p className={`flex items-center gap-2 rounded-md bg-surface-sunken px-3 py-2 text-small text-ink-2 ${className}`}>
        <Icon name="play" /> Video playback isn&apos;t available for this video. The transcript and claims are complete.
      </p>
    );
  }
  return (
    // eslint-disable-next-line jsx-a11y/media-has-caption -- the transcript is the text alternative
    <video ref={videoRef} src={url} controls preload="metadata" onError={onError} className={`max-h-[360px] w-full rounded-md bg-black ${className}`} />
  );
});
