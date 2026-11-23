"use client";

import { forwardRef } from "react";
import { Icon, StanceChip, VerdictChip } from "@/components/ui";
import { clock, evidenceText, type Claim } from "@/lib/api/result-adapter";
import { claimMeaning, EVIDENCE_LEVEL_DISPLAY, studyTypeDisplay } from "@/lib/vocabulary";

const MODALITY: Record<"speech" | "screen", { icon: string; text: string }> = {
  speech: { icon: "mic", text: "Speech" },
  screen: { icon: "screen", text: "On screen" },
};

function Tag({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-line px-1.5 text-cap font-semibold text-ink-2">
      <Icon name={icon} className="!h-3 !w-3" />
      {children}
    </span>
  );
}

type Props = { claim: Claim; active: boolean; onSelect: () => void; onSeek: (s: number) => void };

export const ClaimCard = forwardRef<HTMLElement, Props>(function ClaimCard({ claim: c, active, onSelect, onSeek }, ref) {
  const modalities = c.modality === "both" ? (["speech", "screen"] as const) : c.modality ? [c.modality] : [];
  const quote = c.quotes[0];
  return (
    <article
      ref={ref}
      aria-labelledby={`claim-${c.id}-h`}
      onClick={onSelect}
      className={`flex scroll-mt-20 flex-col gap-3 rounded-lg border bg-surface p-4 ${
        active ? "border-primary shadow-2 outline outline-1 outline-primary" : "border-line shadow-1"
      }`}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 id={`claim-${c.id}-h`} className="text-h3 text-ink">
          Claim {c.number}
        </h3>
        <button type="button" onClick={(e) => { e.stopPropagation(); onSeek(c.start); onSelect(); }} className="font-mono text-small text-primary hover:underline" aria-label={`Play claim ${c.number} from ${clock(c.start)}`}>
          {clock(c.start)}–{clock(c.end)}
        </button>
        {modalities.map((m) => (
          <Tag key={m} icon={MODALITY[m].icon}>
            {MODALITY[m].text}
          </Tag>
        ))}
        {c.deciding && (
          <span className="inline-flex items-center gap-1 rounded-sm bg-ink px-1.5 text-cap font-semibold text-bg">
            <Icon name="star" className="!h-3 !w-3" /> Decided the label
          </span>
        )}
      </header>

      <p className="font-serif text-[17px] leading-[26px] text-ink">{c.text}</p>

      <div className="flex flex-col gap-1.5">
        <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the speaker does</p>
        <div className="flex flex-wrap items-start gap-2">
          {c.stance ? <StanceChip stance={c.stance} /> : <span className="text-small text-ink-2">Not assessed</span>}
          {quote && (
            <span className="text-small text-ink-2">
              <q>{quote.text}</q>{" "}
              <span className="font-mono text-cap text-ink-3">({quote.source === "screen" ? "on screen, " : ""}{clock(quote.start)})</span>
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the evidence shows</p>
        <div className="flex flex-wrap items-center gap-2">
          {c.verdict ? <VerdictChip verdict={c.verdict} /> : <span className="text-small text-ink-2">Not checked</span>}
          <span className="text-small text-ink-2">{evidenceText(c.evidence, EVIDENCE_LEVEL_DISPLAY)}</span>
        </div>
        {c.verdictExplanation && <p className="text-small text-ink">{c.verdictExplanation}</p>}
      </div>

      {c.stance && c.verdict && (
        <p className="border-l-2 border-line-input pl-3 text-small font-medium text-ink">{claimMeaning(c.stance, c.verdict)}</p>
      )}

      {c.sources.length > 0 && (
        // Interim list; chunk 4 replaces it with the claim detail drawer.
        <details onClick={(e) => e.stopPropagation()} className="rounded-md border border-line">
          <summary className="cursor-pointer px-3 py-2 text-small font-semibold text-primary">Sources ({c.sources.length})</summary>
          <ul className="flex flex-col gap-2 px-3 pb-3">
            {c.sources.map((s) => (
              <li key={s.id} className="text-small">
                <span className="font-semibold text-ink-2">{studyTypeDisplay(s.studyType)}</span>
                {" · "}
                {s.relation === "SUPPORTS" ? "Supports" : s.relation === "CONTRADICTS" ? "Contradicts" : "Considered"}
                {" · "}
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-primary underline">
                    {s.title}
                  </a>
                ) : (
                  <span>{s.title} (internal library)</span>
                )}
                {s.year ? ` (${s.year})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
});
