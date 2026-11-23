"use client";

import { Icon } from "@/components/ui";
import { TONE } from "@/components/ui/tone";
import { clock, type Claim } from "@/lib/api/result-adapter";
import { VERDICTS } from "@/lib/vocabulary";

type Props = {
  claims: Claim[];
  duration: number;
  activeId: string | null;
  onSelect: (claim: Claim) => void;
};

/** Segments coloured by verdict, numbered; click to seek. Previous/next give a non-drag alternative (WCAG 2.5.7). */
export function ClaimTimeline({ claims, duration, activeId, onSelect }: Props) {
  const total = Math.max(duration, ...claims.map((c) => c.end), 1);
  const i = claims.findIndex((c) => c.id === activeId);
  const go = (d: number) => {
    const next = claims[i === -1 ? 0 : Math.min(claims.length - 1, Math.max(0, i + d))];
    if (next) onSelect(next);
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-9 rounded-md bg-surface-sunken" role="group" aria-label="Claims along the video">
        {claims.map((c) => {
          const v = c.verdict ? VERDICTS[c.verdict] : null;
          const left = (c.start / total) * 100;
          const width = Math.max(((c.end - c.start) / total) * 100, 3);
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onSelect(c)}
              aria-pressed={c.id === activeId}
              aria-label={`Claim ${c.number}, ${clock(c.start)} to ${clock(c.end)}, ${v ? v.display.toLowerCase() : "not checked"}`}
              className={`absolute top-1 flex h-7 min-w-6 items-center justify-center rounded-sm border text-cap font-bold ${
                v ? TONE[v.tone] : "border-line-input bg-surface text-ink-2"
              } ${v?.dashed ? "border-dashed" : ""} ${c.id === activeId ? "outline outline-2 outline-offset-1 outline-ink" : ""}`}
              style={{ left: `${left}%`, width: `${width}%` }}
            >
              {c.number}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between text-cap text-ink-3">
        <span className="font-mono">0:00</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => go(-1)} disabled={i <= 0} className="inline-flex min-h-8 items-center gap-1 rounded-md border border-line-input bg-surface px-2 text-small text-ink disabled:opacity-50">
            <Icon name="chevr" className="!h-3.5 !w-3.5 rotate-180" /> Previous claim
          </button>
          <button type="button" onClick={() => go(1)} disabled={i === claims.length - 1} className="inline-flex min-h-8 items-center gap-1 rounded-md border border-line-input bg-surface px-2 text-small text-ink disabled:opacity-50">
            Next claim <Icon name="chevr" className="!h-3.5 !w-3.5" />
          </button>
        </div>
        <span className="font-mono">{clock(total)}</span>
      </div>
    </div>
  );
}
