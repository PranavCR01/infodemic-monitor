// GET /v1/stats?window=… (T62). Any signed-in role; 401 without a valid token.
import { apiFetch } from "@/lib/api";
import type { StatsWindow } from "@/lib/vocabulary";
import { adaptStats, type StatsModel } from "./stats-adapter";
import type { RawStats } from "./stats-types";

export type StatsLoad = { kind: "ok"; data: StatsModel } | { kind: "sign-in" } | { kind: "error"; message: string };

export async function fetchStats(window: StatsWindow): Promise<StatsLoad> {
  try {
    const res = await apiFetch(`/v1/stats?window=${encodeURIComponent(window)}`);
    if (res.status === 401) return { kind: "sign-in" };
    if (!res.ok) return { kind: "error", message: "The figures aren't available right now. Try again in a moment." };
    return { kind: "ok", data: adaptStats((await res.json()) as RawStats) };
  } catch {
    return { kind: "error", message: "The figures couldn't be loaded: no connection." };
  }
}
