// Polling schedule (HANDOFF §6.4). Pure, so the rules are unit-tested; the hook in
// lib/hooks/usePolling.ts only runs it.
//
// - every 3 s for the first 3 minutes, then every 10 s;
// - after 3 failed polls in a row: "lost connection", backing off 3 → 10 → 20 s;
// - stop once the job is done;
// - paused while the tab is hidden (the hook), polled at once on focus (the hook).

export const FAST_MS = 3_000;
export const SLOW_MS = 10_000;
export const FAST_FOR_MS = 180_000;
export const LOST_AFTER = 3;
const BACKOFF_MS = [3_000, 10_000, 20_000];

export type PollState = { elapsedMs: number; failures: number; done: boolean };

/** Milliseconds until the next poll, or null to stop. */
export function nextDelay({ elapsedMs, failures, done }: PollState, base?: { fastMs?: number; slowMs?: number }): number | null {
  if (done) return null;
  if (failures >= LOST_AFTER) return BACKOFF_MS[Math.min(failures - LOST_AFTER, BACKOFF_MS.length - 1)];
  return elapsedMs < FAST_FOR_MS ? base?.fastMs ?? FAST_MS : base?.slowMs ?? SLOW_MS;
}

export const isLost = (failures: number) => failures >= LOST_AFTER;
