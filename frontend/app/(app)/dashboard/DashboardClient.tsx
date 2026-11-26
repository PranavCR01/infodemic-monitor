"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { Button, ErrorBanner, Icon } from "@/components/ui";
import { fetchStats, type StatsLoad } from "@/lib/api/stats";
import { DASHBOARD_NOTE, STATS_WINDOWS, STATS_WINDOW_DISPLAY, type StatsWindow } from "@/lib/vocabulary";

/** T62. Any signed-in role; every role sees the same totals. 401 goes to sign-in. */
export function DashboardClient() {
  const router = useRouter();
  const [win, setWin] = useState<StatsWindow>("30d");
  const [state, setState] = useState<StatsLoad | null>(null);
  const latest = useRef(0);

  const load = useCallback(async (w: StatsWindow) => {
    const id = ++latest.current;
    setState(null);
    const r = await fetchStats(w);
    // A slower answer for an earlier window never replaces the current one.
    if (id === latest.current) setState(r);
  }, []);

  useEffect(() => {
    void load(win);
  }, [win, load]);

  useEffect(() => {
    if (state?.kind === "sign-in") router.replace(`/sign-in?next=${encodeURIComponent("/dashboard")}`);
  }, [state, router]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-h1 text-ink">Dashboard</h1>
          <p className="text-small text-ink-2">Totals across everyone&apos;s uploads. No individual video or uploader is shown.</p>
        </div>
        <div role="group" aria-label="Time window" className="inline-flex max-w-full flex-wrap rounded-md border border-line-input">
          {STATS_WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              aria-pressed={win === w}
              onClick={() => setWin(w)}
              className={`min-h-10 px-3 text-small font-semibold first:rounded-l-md last:rounded-r-md ${win === w ? "bg-ink text-bg" : "bg-surface text-ink-2 hover:text-ink"}`}
            >
              {STATS_WINDOW_DISPLAY[w]}
            </button>
          ))}
        </div>
      </div>

      <p role="note" className="flex items-start gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small font-semibold text-warn-fg">
        <Icon name="info" className="mt-0.5 shrink-0" />
        {DASHBOARD_NOTE}
      </p>

      {state === null || state.kind === "sign-in" ? (
        <p className="text-small text-ink-2" role="status" aria-busy="true">
          {state === null ? "Loading the figures…" : "Your session has ended. Taking you to sign in…"}
        </p>
      ) : state.kind === "error" ? (
        <ErrorBanner
          title="The figures couldn't be loaded."
          action={
            <Button variant="secondary" size="sm" onClick={() => void load(win)}>
              Try again
            </Button>
          }
        >
          {state.message}
        </ErrorBanner>
      ) : (
        <Dashboard stats={state.data} />
      )}
    </div>
  );
}
