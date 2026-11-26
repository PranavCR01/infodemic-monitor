import type { ReactNode } from "react";
import { Icon } from "@/components/ui";
import { cellSpoken, cellText, formatHours, formatShare, type Cell, type StatsModel } from "@/lib/api/stats-adapter";
import { STATS_WINDOW_DISPLAY } from "@/lib/vocabulary";
import { BarTable } from "./BarTable";

const NOT_ENOUGH = "Not enough decisions";

/**
 * T62: totals across every user's uploads (§7ah). Aggregates only: nothing here names or
 * links to a video, a job or an uploader.
 */
export function Dashboard({ stats: s }: { stats: StatsModel }) {
  const windowText = s.window === "all" ? "all time" : `the last ${STATS_WINDOW_DISPLAY[s.window]}`;
  const misinfo = s.labels.find((l) => l.key === "MISINFO")!.cell;
  const share = formatShare(s.reviews.changedShare);
  const median = formatHours(s.reviews.medianHours);

  return (
    <div className="flex flex-col gap-6">
      <p className="text-small text-ink-2">
        Figures for {windowText}
        {s.windowStart ? ` (${day(s.windowStart)} to ${day(s.windowEnd)})` : ""}. Counts under 5 are shown as &lt;5 so no single upload can be
        picked out. Updated {time(s.generatedAt)}.
      </p>

      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Summary">
        <StatCard label="Videos analysed" cell={s.videosTotal} sub={`In ${windowText}`} />
        <StatCard label="Waiting for a reviewer" cell={s.reviews.backlogNow} sub="Right now" />
        <StatCard label="Reviewer decisions" cell={s.reviews.decisions} sub={`In ${windowText}`} />
        <StatCard label="Failed analyses" cell={s.jobs.failed} sub={`In ${windowText}`} />
      </ul>

      <Section id="weekly" title="Videos analysed per week">
        {s.videosTotal.suppressed ? (
          <Hidden>Fewer than 5 videos were analysed in this window, so the weekly figures are hidden.</Hidden>
        ) : s.perWeek.length === 0 ? (
          <Hidden>No weeks in this window.</Hidden>
        ) : (
          <BarTable caption="Videos analysed per week" labelHeader="Week" rows={s.perWeek} />
        )}
      </Section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section id="labels" title="Labels given by the system" sub="The system's label, before any reviewer correction.">
          {s.videosTotal.suppressed ? (
            <Hidden>Fewer than 5 videos in this window, so the labels are hidden.</Hidden>
          ) : (
            <BarTable caption="Videos by label" labelHeader="Label" rows={s.labels} />
          )}
          <h3 className="mt-4 text-h3 text-ink">How MISINFO was decided</h3>
          {misinfo.suppressed ? (
            <Hidden>Fewer than 5 videos were labelled MISINFO, so this split is hidden.</Hidden>
          ) : (
            <BarTable caption="MISINFO videos by basis" labelHeader="Basis" rows={s.misinfoBasis} />
          )}
        </Section>

        <Section id="categories" title="Most common claim types" sub="Videos with at least one claim of each type. Types with fewer than 5 videos are left out.">
          {s.categories.length === 0 ? (
            <Hidden>No claim type reached 5 videos in this window.</Hidden>
          ) : (
            <BarTable caption="Videos by claim type" labelHeader="Claim type" rows={s.categories} />
          )}
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section id="reviews" title="Reviews">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-small min-[420px]:grid-cols-2">
            <Figure term="Waiting for a reviewer (now)">
              <CellText cell={s.reviews.backlogNow} />
            </Figure>
            <Figure term="Decisions in this window">
              <CellText cell={s.reviews.decisions} />
            </Figure>
            <Figure term="Decisions that changed the system's label">
              <CellText cell={s.reviews.changed} />
            </Figure>
            <Figure term="Decisions that kept it">
              <CellText cell={s.reviews.kept} />
            </Figure>
            <Figure term="Share that changed the label">
              {share ?? <NotEnough />}
            </Figure>
            <Figure term="Median time to a decision">
              {median ?? <NotEnough />}
            </Figure>
          </dl>
        </Section>

        <Section id="jobs" title="Analysis jobs">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-small min-[420px]:grid-cols-2">
            <Figure term="Waiting to start (now)">
              <CellText cell={s.jobs.pendingNow} />
            </Figure>
            <Figure term="Running (now)">
              <CellText cell={s.jobs.runningNow} />
            </Figure>
            <Figure term="Failed in this window">
              <CellText cell={s.jobs.failed} />
            </Figure>
          </dl>
          <p className="mt-3 text-cap text-ink-3">&ldquo;Now&rdquo; figures are a snapshot of this moment, whatever window is chosen.</p>
        </Section>
      </div>
    </div>
  );
}

function StatCard({ label, cell, sub }: { label: string; cell: Cell; sub: string }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-4 shadow-1">
      <span className="text-small font-semibold text-ink-2">{label}</span>
      <span className="font-serif text-h1 tabular-nums text-ink" data-cell={cell.suppressed ? "suppressed" : cell.n}>
        <span aria-hidden="true">{cellText(cell)}</span>
        <span className="sr-only">{cellSpoken(cell)}</span>
      </span>
      <span className="text-cap text-ink-3">{sub}</span>
    </li>
  );
}

function CellText({ cell }: { cell: Cell }) {
  return (
    <span className="tabular-nums" data-cell={cell.suppressed ? "suppressed" : cell.n}>
      <span aria-hidden="true">{cellText(cell)}</span>
      <span className="sr-only">{cellSpoken(cell)}</span>
    </span>
  );
}

function NotEnough() {
  return (
    <span className="text-ink-3" data-null="true">
      {NOT_ENOUGH}
      <span className="block text-cap">Shown once there are 5 or more decisions.</span>
    </span>
  );
}

function Figure({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-ink-2">{term}</dt>
      <dd className="text-h3 text-ink">{children}</dd>
    </div>
  );
}

function Section({ id, title, sub, children }: { id: string; title: string; sub?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`dash-${id}`} className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface p-4 shadow-1">
      <h2 id={`dash-${id}`} className="text-h2 text-ink">
        {title}
      </h2>
      {sub && <p className="text-cap text-ink-3">{sub}</p>}
      {children}
    </section>
  );
}

function Hidden({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-1.5 rounded-md bg-surface-sunken px-3 py-2 text-small text-ink-2">
      <Icon name="lock" className="mt-0.5 !h-3.5 !w-3.5" />
      {children}
    </p>
  );
}

const day = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
};
const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC", timeZoneName: "short" });
};
