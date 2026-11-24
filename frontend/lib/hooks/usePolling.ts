"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isLost, nextDelay } from "@/lib/polling";

/**
 * Run `poll` on the §6.4 schedule. `poll` resolves true when it got an answer and
 * false when it failed; `done` stops the loop. Paused while the tab is hidden,
 * polled at once when the tab comes back. Returns `lost` (3 failures in a row) and
 * `checkNow` for the "Check now" button.
 */
export function usePolling(poll: () => Promise<boolean>, done: boolean, base?: { fastMs?: number; slowMs?: number }) {
  const [failures, setFailures] = useState(0);
  // Bumped after every poll (or skipped poll), so the timer re-arms even when
  // `failures` doesn't change (0 → 0 after a success).
  const [tick, setTick] = useState(0);
  const started = useRef(Date.now());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef(poll);
  pollRef.current = poll;
  const fast = base?.fastMs;
  const slow = base?.slowMs;

  const run = useCallback(async () => {
    let ok = false;
    try {
      ok = await pollRef.current();
    } catch {
      ok = false;
    }
    setFailures((f) => (ok ? 0 : f + 1));
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const delay = nextDelay({ elapsedMs: Date.now() - started.current, failures, done }, { fastMs: fast, slowMs: slow });
    if (delay === null) return;
    timer.current = setTimeout(() => {
      if (!document.hidden) void run();
      else setTick((t) => t + 1); // hidden: skip this poll, keep the schedule
    }, delay);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [tick, failures, done, run, fast, slow]);

  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden && !done) void run();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [done, run]);

  return { lost: isLost(failures), checkNow: run };
}
