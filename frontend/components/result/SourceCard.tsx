import { Icon } from "@/components/ui";
import { TONE } from "@/components/ui/tone";
import type { BlindSource } from "@/lib/api/blind-material";
import type { Source } from "@/lib/api/result-adapter";
import { studyTypeDisplay } from "@/lib/vocabulary";

const KIND: Record<Source["kind"], { icon: string; text: string }> = {
  pubmed: { icon: "book", text: "PubMed paper" },
  reference: { icon: "landmark", text: "Official reference" },
  library: { icon: "archive", text: "Internal library" },
  other: { icon: "file", text: "Other source" },
};

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "the source";
  }
}

/**
 * One source (HANDOFF §4 SourceCard). Internal library documents are dashed, "Internal only", never linked.
 * A BlindSource (T40) has no relation, so no Supports / Contradicts badge can show.
 */
export function SourceCard({ s }: { s: Source | BlindSource }) {
  const internal = s.kind === "library";
  const kind = KIND[s.kind];
  const typeTag = s.level === "GUIDANCE" ? "Official guidance" : studyTypeDisplay(s.studyType);
  const relation = "relation" in s ? s.relation : null;
  const supports = relation === "SUPPORTS";
  return (
    <article className={`flex flex-col gap-2 rounded-lg border bg-surface px-4 py-3.5 ${internal ? "border-dashed border-line-input" : "border-line"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-cap font-semibold text-ink-2">
          <Icon name={kind.icon} className="!h-3.5 !w-3.5" />
          {kind.text}
          {s.kind === "reference" && s.publisher ? ` · ${s.publisher}` : ""}
        </span>
        <span className="rounded-sm border border-line-input px-1.5 text-cap font-semibold text-ink">{typeTag}</span>
        {(relation === "SUPPORTS" || relation === "CONTRADICTS") && (
          <span className={`ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-cap font-semibold ${TONE[supports ? "nomisinfo" : "misinfo"]}`}>
            <Icon name={supports ? "checkc" : "xc"} className="!h-3.5 !w-3.5" />
            {supports ? "Supports" : "Contradicts"}
          </span>
        )}
      </div>
      <h4 className="text-h3 text-ink">{s.title}</h4>
      {(s.publisher || s.year) && s.kind !== "reference" && (
        <p className="text-small text-ink-2">{[s.publisher, s.year].filter(Boolean).join(" · ")}</p>
      )}
      {s.kind === "reference" && s.year && <p className="text-small text-ink-2">{s.year}</p>}
      {s.snippet && (
        <blockquote className="rounded-md border border-line bg-surface-2 px-3 py-2 text-small text-ink">
          “{s.snippet}”
        </blockquote>
      )}
      {internal ? (
        <p className="text-cap font-semibold text-ink-2">Internal only. Not available outside the project.</p>
      ) : s.url ? (
        <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-small text-primary underline">
          {s.kind === "pubmed" ? "View on PubMed" : `Open on ${hostOf(s.url)}`}
          <Icon name="ext" className="!h-3.5 !w-3.5" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      ) : null}
    </article>
  );
}

const ORDER: (Source["level"])[] = ["SYSTEMATIC_REVIEW", "RCT", "GUIDANCE", "OBSERVATIONAL", "ANIMAL_LAB", null];

/** Strongest kind of study first, not most numerous (HANDOFF §6.6). */
export function sortSources(sources: Source[]): Source[] {
  const rank = (s: Source) => ORDER.indexOf(s.level);
  return [...sources].sort((a, b) => rank(a) - rank(b) || (b.year ?? 0) - (a.year ?? 0));
}
