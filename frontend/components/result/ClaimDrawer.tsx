"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import { Icon, StanceChip, VerdictChip, buttonClass } from "@/components/ui";
import { clock, type Claim, type Segment, type Source } from "@/lib/api/result-adapter";
import { claimMeaning, STANCES } from "@/lib/vocabulary";
import { ClaimSearch } from "./ClaimSearch";
import { SourceCard, sortSources } from "./SourceCard";

type Props = {
  claims: Claim[];
  openId: string | null;
  transcript: Segment[];
  onNavigate: (id: string) => void;
  onClose: () => void;
  onPlay: (seconds: number) => void;
};

type Direction = "CONTRADICTS" | "SUPPORTS";

/** id of a claim card's "details" button, so focus can come back to it. */
export const openButtonId = (claimId: string) => `claim-${claimId}-open`;

/** Which list to open on: the one that matches the verdict, else the longer one. */
export function defaultDirection(c: Claim): Direction {
  if (c.verdict === "SUPPORTED") return "SUPPORTS";
  if (c.verdict === "CONTRADICTED") return "CONTRADICTS";
  return c.evidence.supports > c.evidence.contradicts ? "SUPPORTS" : "CONTRADICTS";
}

function quotesFor(c: Claim, transcript: Segment[]): Segment[] {
  if (c.quotes.length) return c.quotes;
  return transcript.filter((s) => c.sourceSegmentIds.includes(s.id));
}

/**
 * Claim detail (ClaimDetail.dc.html): a right-hand drawer up to 640 px, full width on
 * phones. Radix Dialog gives role="dialog", the focus trap and Esc to close.
 */
export function ClaimDrawer({ claims, openId, transcript, onNavigate, onClose, onPlay }: Props) {
  const i = claims.findIndex((c) => c.id === openId);
  const c = i >= 0 ? claims[i] : null;
  const [dir, setDir] = useState<Direction>("CONTRADICTS");
  const [copied, setCopied] = useState(false);
  const lastShown = useRef<string | null>(null);
  if (c) lastShown.current = c.id;

  useEffect(() => {
    if (c) setDir(defaultDirection(c));
    setCopied(false);
  }, [c]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const modalities = c?.modality === "both" ? ["Speech", "On screen"] : c?.modality === "screen" ? ["On screen"] : c?.modality === "speech" ? ["Speech"] : [];
  const shown: Source[] = c ? sortSources(c.sources.filter((s) => s.relation === dir)) : [];
  const counts = c ? { CONTRADICTS: c.evidence.contradicts, SUPPORTS: c.evidence.supports } : { CONTRADICTS: 0, SUPPORTS: 0 };

  return (
    <Dialog.Root open={Boolean(c)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={(e) => {
            // Opened from code, not a Dialog.Trigger, so Radix has nowhere to return focus.
            // Return it to the "details" button of the claim last shown (WCAG 2.4.3).
            e.preventDefault();
            if (lastShown.current) document.getElementById(openButtonId(lastShown.current))?.focus();
          }}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface shadow-3 sm:max-w-[640px] sm:border-l sm:border-line md:max-w-[90vw] lg:max-w-[640px]"
        >
          {c && (
            <>
              <div className="flex items-center gap-2 border-b border-line py-3 pl-6 pr-4">
                <span className="text-cap font-semibold uppercase tracking-wider text-ink-3">
                  Claim {c.number} of {claims.length}
                </span>
                <button type="button" aria-label="Previous claim" disabled={i <= 0} onClick={() => onNavigate(claims[i - 1].id)} className={buttonClass("ghost", "sm", "ml-auto min-h-11 min-w-11")}>
                  <Icon name="chevr" className="rotate-180" />
                </button>
                <button type="button" aria-label="Next claim" disabled={i >= claims.length - 1} onClick={() => onNavigate(claims[i + 1].id)} className={buttonClass("ghost", "sm", "min-h-11 min-w-11")}>
                  <Icon name="chevr" />
                </button>
                <Dialog.Close aria-label="Close claim detail" className={buttonClass("ghost", "sm", "min-h-11 min-w-11")}>
                  <Icon name="x" />
                </Dialog.Close>
              </div>

              <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-6 pb-8 pt-5">
                <div className="flex flex-col gap-2.5">
                  <Dialog.Title className="font-serif text-[22px] font-semibold leading-[30px] text-ink">{c.text}</Dialog.Title>
                  <div className="flex flex-wrap items-center gap-2">
                    <button type="button" onClick={() => onPlay(c.start)} className={buttonClass("secondary", "sm")}>
                      <Icon name="play" className="!h-3.5 !w-3.5" />
                      Play <span className="font-mono">{clock(c.start)}–{clock(c.end)}</span>
                    </button>
                    {modalities.map((m) => (
                      <span key={m} className="rounded-sm border border-line px-1.5 text-cap font-semibold text-ink-2">
                        {m}
                      </span>
                    ))}
                    {c.deciding && (
                      <span className="inline-flex items-center gap-1 rounded-sm bg-ink px-1.5 text-cap font-semibold text-bg">
                        <Icon name="star" className="!h-3 !w-3" /> Decided the label
                      </span>
                    )}
                  </div>
                </div>

                <section aria-labelledby="d-stance" className="flex flex-col gap-2.5">
                  <h3 id="d-stance" className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the speaker does</h3>
                  {c.stance ? (
                    <div className="flex flex-wrap items-center gap-2.5">
                      <StanceChip stance={c.stance} />
                      <span className="text-small text-ink-2">{STANCES[c.stance].description}.</span>
                    </div>
                  ) : (
                    <p className="text-small text-ink-2">The speaker&apos;s stance wasn&apos;t assessed.</p>
                  )}
                  {quotesFor(c, transcript).map((q) => (
                    <p key={`${q.source}-${q.id}`} className="flex gap-2 rounded-md border-l-2 border-line-input bg-surface-2 px-3 py-2 text-small text-ink">
                      <Icon name={q.source === "screen" ? "screen" : "mic"} className="mt-0.5 !h-3.5 !w-3.5 text-ink-3" />
                      <span>
                        <q className={q.source === "screen" ? "uppercase" : ""}>{q.text}</q>{" "}
                        <span className="font-mono text-cap text-ink-3">
                          {q.source === "screen" ? "on screen, " : ""}
                          {clock(q.start)}
                        </span>
                      </span>
                    </p>
                  ))}
                  {c.stanceRationale && <p className="text-small text-ink-2">{c.stanceRationale}</p>}
                </section>

                <section aria-labelledby="d-ev" className="flex flex-col gap-2.5">
                  <h3 id="d-ev" className="text-cap font-semibold uppercase tracking-wider text-ink-3">What the evidence shows</h3>
                  <div className="flex flex-wrap items-center gap-2.5">
                    {c.verdict ? <VerdictChip verdict={c.verdict} /> : <span className="text-small text-ink-2">Not checked</span>}
                    <span className="text-small tabular-nums text-ink-2">
                      {c.evidence.contradicts} {c.evidence.contradicts === 1 ? "source contradicts" : "sources contradict"} · {c.evidence.supports}{" "}
                      {c.evidence.supports === 1 ? "supports" : "support"}
                    </span>
                  </div>
                  {c.verdictExplanation && <p className="text-body text-ink">{c.verdictExplanation}</p>}
                  {c.stance && c.verdict && <p className="border-l-2 border-line-input pl-3 text-small font-medium text-ink">{claimMeaning(c.stance, c.verdict)}</p>}
                  {c.limitations.length > 0 && (
                    <div className="flex gap-2 rounded-lg border border-nomisinfo-bd bg-primary-subtle px-3 py-2.5 text-small text-ink">
                      <Icon name="info" className="mt-0.5 !h-3.5 !w-3.5 text-primary" />
                      <div>
                        <strong>Limitations.</strong> {c.limitations.join(" ")}
                      </div>
                    </div>
                  )}
                </section>

                <section aria-labelledby="d-src" className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 id="d-src" className="text-cap font-semibold uppercase tracking-wider text-ink-3">Sources</h3>
                    <div role="group" aria-label="Filter sources" className="ml-auto inline-flex rounded-md border border-line-input">
                      {(["CONTRADICTS", "SUPPORTS"] as const).map((d) => (
                        <button
                          key={d}
                          type="button"
                          aria-pressed={dir === d}
                          onClick={() => setDir(d)}
                          className={`min-h-9 px-3 text-small font-semibold first:rounded-l-md last:rounded-r-md ${dir === d ? "bg-ink text-bg" : "bg-surface text-ink-2 hover:text-ink"}`}
                        >
                          {d === "CONTRADICTS" ? "Contradicts" : "Supports"} <span className="tabular-nums">{counts[d]}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                  {shown.map((s) => (
                    <SourceCard key={s.id} s={s} />
                  ))}
                  {shown.length === 0 && (
                    <p className="text-small text-ink-2">
                      {c.sources.length === 0
                        ? "No source was found that tests this claim."
                        : dir === "SUPPORTS"
                          ? "No source supports this claim."
                          : "No source contradicts this claim."}
                    </p>
                  )}
                </section>

                {c.search && <ClaimSearch s={c.search} />}

                {c.criticNotes.length > 0 && (
                  <details className="border-t border-line pt-3">
                    <summary className="cursor-pointer text-small font-semibold text-ink-2">
                      Critic&apos;s notes <span className="tabular-nums">({c.criticNotes.length})</span>
                    </summary>
                    <ul className="mt-2 list-disc pl-6 text-small text-ink-2">
                      {c.criticNotes.map((n, k) => (
                        <li key={k}>{n}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface-2 px-6 py-3">
                <button type="button" onClick={copyLink} className={buttonClass("secondary", "sm")}>
                  <Icon name="link" className="!h-3.5 !w-3.5" /> Copy link to claim
                </button>
                <span role="status" className="text-small text-ink-2">
                  {copied ? "Link copied." : ""}
                </span>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
