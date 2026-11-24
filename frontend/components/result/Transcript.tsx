"use client";

import { claimsForSegment, clock, type Claim, type Segment } from "@/lib/api/result-adapter";
import { Icon } from "@/components/ui";

type Props = {
  segments: Segment[];
  claims: Claim[];
  activeId: string | null;
  onSeek: (seconds: number) => void;
  onSelect: (claim: Claim) => void;
};

/** Speech and on-screen text in time order. Rows behind the selected claim are tinted. */
export function Transcript({ segments, claims, activeId, onSeek, onSelect }: Props) {
  if (segments.length === 0) {
    return <p className="text-small text-ink-2">No transcript is available for this video.</p>;
  }
  return (
    <ol className="flex flex-col">
      {segments.map((s) => {
        const linked = claimsForSegment(claims, s);
        const active = linked.some((c) => c.id === activeId);
        return (
          <li
            key={`${s.source}-${s.id}`}
            className={`grid grid-cols-[52px_minmax(0,1fr)] gap-x-3 border-b border-line px-2 py-2.5 ${active ? "bg-primary-subtle" : ""}`}
          >
            <button type="button" onClick={() => onSeek(s.start)} className="self-start text-left font-mono text-small text-primary underline-offset-2 hover:underline" aria-label={`Play from ${clock(s.start)}`}>
              {clock(s.start)}
            </button>
            <div className="flex flex-col gap-1">
              {s.source === "screen" && (
                <span className="inline-flex w-fit items-center gap-1 rounded-sm border border-line px-1.5 text-cap font-semibold text-ink-2">
                  <Icon name="screen" className="!h-3 !w-3" /> On screen
                </span>
              )}
              <p className={`font-serif text-transcript text-ink ${s.source === "screen" ? "uppercase tracking-wide" : ""}`}>{s.text}</p>
              {linked.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {linked.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => onSelect(c)}
                      aria-pressed={c.id === activeId}
                      className="rounded-sm border border-line-input bg-surface px-1.5 text-cap font-semibold text-ink-2 hover:text-ink"
                    >
                      Claim {c.number}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
