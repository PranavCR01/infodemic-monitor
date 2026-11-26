// ADAPTER: GET /jobs/{job_id}/result → the view model the result page renders.
//
// The page never reads the raw response. Everything that can go wrong with the
// API's values is handled here, once: unknown enums, missing T26/T30/T31 fields,
// internal names in free text, claim ordering and numbering. When the backend
// shape changes, this file changes; the components don't.

import { cleanClaimText, cleanTitle, formatPubDate, replaceEvidenceIds, type NamedSource } from "@/lib/report-text";
import {
  displayText,
  evidenceLevel,
  isMisinfoBasis,
  isStance,
  isVerdict,
  isVideoLabel,
  reasonText,
  studyTypeCount,
  studyTypeKey,
  toJobState,
  toReviewStatus,
  type EvidenceLevel,
  type MisinfoBasis,
  type ReviewStatus,
  type Severity,
  type Stance,
  type Verdict,
  type VideoLabel,
  isSeverity,
} from "@/lib/vocabulary";
import type { RawClaim, RawEvidence, RawReason, RawResult, RawSearchTrail, RawSegment } from "./result-types";

export type SourceKind = "pubmed" | "reference" | "library" | "other";

export type Source = {
  id: string;
  title: string;
  relation: "SUPPORTS" | "CONTRADICTS" | "CONSIDERED";
  studyType: string | null;
  level: EvidenceLevel | "GUIDANCE" | null;
  kind: SourceKind;
  year: number | null;
  publisher: string | null;
  snippet: string;
  url: string | null;
  pmid: string | null;
  /** T65: PubMed journal abbreviation, when the result has it. */
  journal: string | null;
  /** T65: publication date, formatted ("5 Nov 2026", "Nov 2026", "2026"), when the result has it. */
  pubDate: string | null;
};

export type Segment = {
  id: string;
  source: "speech" | "screen";
  start: number;
  end: number;
  text: string;
};

export type EvidenceSummary = {
  supports: number;
  contradicts: number;
  /** Best levels found, per direction, strongest first. */
  levels: { level: EvidenceLevel; direction: "supports" | "contradicts"; count: number }[];
  guidance: { direction: "supports" | "contradicts"; count: number }[];
  /** T65: sources with no strip level, counted by the same study type the source list shows. */
  others: { studyType: string; direction: "supports" | "contradicts"; count: number }[];
};

/** "The speaker says": the backend's best-overlap words (T65), else the first stance quote. */
export type SpeakerQuote = { text: string; at: number | null; source: "speech" | "screen" | null };

/** "How we searched" for one claim (T31). */
export type ClaimSearch = {
  /** Distinct queries only: rounds that repeated an earlier query are left out. */
  queries: { query: string; results: number | null; failed: boolean }[];
  /** Every round as run, repeats included, for the review screen's technical details. */
  rounds: { round: number; query: string; results: number | null; failed: boolean; repeat: boolean }[];
  sources: { name: string; publisher: string; sites: string[] }[];
  libraryUsed: boolean;
  retrieved: number | null;
  screened: number;
  kept: number;
  roundsUsed: number;
  roundsMax: number;
  budgetExhausted: boolean;
  /** Older runs kept only the planned queries, not what each returned. */
  partial: boolean;
};

export type Claim = {
  id: string; // claim_id, unique within the result
  number: number; // 1-based, in time order: what the UI calls it
  text: string;
  start: number;
  end: number;
  deciding: boolean;
  stance: Stance | null;
  verdict: Verdict | null;
  verdictExplanation: string;
  limitations: string[];
  stanceRationale: string;
  quotes: Segment[];
  speakerQuote: SpeakerQuote | null;
  modality: "speech" | "screen" | "both" | null;
  sourceSegmentIds: string[];
  sources: Source[];
  evidence: EvidenceSummary;
  criticNotes: string[];
  severity: Severity | null;
  search: ClaimSearch | null;
};

export type PreviousAnalysis = {
  jobId: string;
  finishedAt: string | null;
  label: VideoLabel | null;
  basis: MisinfoBasis | null;
  pipelineVersion: string | null;
  /** Rejected by a reviewer: the API can't open its result (GET /jobs/{id}/result answers 202). */
  rejected: boolean;
};

export type Versions = {
  /** Earlier finished analyses, newest first (as the API sends them). */
  previous: PreviousAnalysis[];
  /** False on an older version: link to currentJobId. */
  isCurrent: boolean;
  currentJobId: string | null;
  /** A newer run of this video that is still going, or that failed. */
  latest: { jobId: string; running: boolean; failed: boolean } | null;
};

export type Reason = { code: string; claimNumber: number | null; text: string };

export type ResultModel = {
  jobId: string;
  videoId: string | null;
  filename: string;
  label: VideoLabel | null;
  basis: MisinfoBasis | null;
  /** The reviewer's label when a case was corrected, else null. */
  correctedLabel: VideoLabel | null;
  explanation: string;
  decisionRule: string | null;
  reviewStatus: ReviewStatus;
  reviewDecidedAt: string | null;
  reviewSeverity: Severity | null;
  /** T55: the newer job that superseded this result's review case. */
  supersededByJobId: string | null;
  /** T33: the job's owner (Supabase user id), for who may re-analyse. */
  submittedBy: string | null;
  /** T55: versions of this video's analysis. */
  versions: Versions;
  reasons: Reason[];
  claims: Claim[];
  decidingClaims: Claim[];
  transcript: Segment[]; // speech and on-screen text, in time order
  hasClaimLevel: boolean; // false for single-call / fallback results
  submittedAt: string | null;
  analysedAt: string | null;
  /** Pipeline / prompt version, for tracing a printed report. Never a model ID. */
  analysisVersion: string | null;
  /** All claims' searches together (T31), for the result page and the report. */
  search: {
    queries: string[];
    sites: string[];
    screened: number | null;
    kept: number | null;
    ranAt: string | null;
  } | null;
};

const LEVEL_ORDER: EvidenceLevel[] = ["SYSTEMATIC_REVIEW", "RCT", "OBSERVATIONAL", "ANIMAL_LAB"];

function toRelation(r: string): Source["relation"] {
  return r === "SUPPORTS" || r === "CONTRADICTS" ? r : "CONSIDERED";
}

function toSource(e: RawEvidence): Source {
  const kind: SourceKind = e.source_kind ?? (e.pmid ? "pubmed" : "other");
  return {
    id: e.evidence_id,
    title: cleanTitle(e.title) || (e.pmid ? `PMID ${e.pmid}` : "Untitled source"),
    relation: toRelation(e.relation),
    studyType: e.study_type ?? null,
    level: evidenceLevel(e.study_type),
    kind,
    year: e.year ?? null,
    publisher: e.publisher ?? null,
    snippet: e.abstract_snippet ?? "",
    // Internal library documents never get an external link (HANDOFF §4 SourceCard).
    url: kind === "library" ? null : e.url ?? (e.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${e.pmid}/` : null),
    pmid: e.pmid ?? null,
    journal: e.journal?.trim() || null,
    pubDate: formatPubDate(e.pub_date),
  };
}

/** The source line under a title: journal (or publisher) and date (or year), whichever exist. */
export function sourceMeta(s: Pick<Source, "kind" | "publisher" | "year"> & Partial<Pick<Source, "journal" | "pubDate">>): string[] {
  const where = s.journal || (s.kind !== "reference" ? s.publisher : null);
  const when = s.pubDate || (s.year ? String(s.year) : null);
  return [where, when].filter((x): x is string => Boolean(x));
}

function toSpeakerQuote(raw: string | null | undefined, quotes: Segment[]): SpeakerQuote | null {
  const text = raw?.trim();
  if (text) {
    const seg = quotes.find((q) => q.text.trim() === text) ?? null;
    return { text, at: seg?.start ?? null, source: seg?.source ?? null };
  }
  const q = quotes[0];
  return q ? { text: q.text, at: q.start, source: q.source } : null;
}

export function summariseEvidence(sources: Source[]): EvidenceSummary {
  const directional = sources.filter((s) => s.relation !== "CONSIDERED");
  const dir = (s: Source) => (s.relation === "SUPPORTS" ? "supports" : "contradicts") as "supports" | "contradicts";
  const levels: EvidenceSummary["levels"] = [];
  for (const level of LEVEL_ORDER) {
    for (const direction of ["contradicts", "supports"] as const) {
      const count = directional.filter((s) => s.level === level && dir(s) === direction).length;
      if (count) levels.push({ level, direction, count });
    }
  }
  const guidance = (["contradicts", "supports"] as const)
    .map((direction) => ({ direction, count: directional.filter((s) => s.level === "GUIDANCE" && dir(s) === direction).length }))
    .filter((g) => g.count > 0);
  const others: EvidenceSummary["others"] = [];
  for (const direction of ["contradicts", "supports"] as const) {
    const counts = new Map<string, number>();
    for (const s of directional) if (s.level === null && dir(s) === direction) counts.set(studyTypeKey(s.studyType), (counts.get(studyTypeKey(s.studyType)) ?? 0) + 1);
    counts.forEach((count, studyType) => others.push({ studyType, direction, count }));
  }
  return {
    supports: directional.filter((s) => s.relation === "SUPPORTS").length,
    contradicts: directional.filter((s) => s.relation === "CONTRADICTS").length,
    levels,
    guidance,
    others,
  };
}

function toVersions(raw: RawResult): Versions {
  const latest = raw.latest_job;
  const latestState = latest ? toJobState(latest.state ?? latest.status) : null;
  return {
    previous: (raw.previous_jobs ?? []).map((p) => {
      const label = isVideoLabel(p.label) ? p.label : null;
      return {
        jobId: p.job_id,
        finishedAt: p.finished_at ?? null,
        label,
        // "MISINFO (unproven)" etc. comes from label_display; read the basis back from it.
        basis: label === "MISINFO" ? basisFromDisplay(p.label_display) : null,
        pipelineVersion: p.pipeline_version ?? null,
        rejected: p.status === "FAILED",
      };
    }),
    isCurrent: raw.is_current ?? true,
    currentJobId: raw.current_job_id ?? null,
    latest:
      latest && latest.job_id !== raw.job_id
        ? { jobId: latest.job_id, running: latestState === "QUEUED" || latestState === "RUNNING" || latestState === "RETRYING", failed: latestState === "FAILED" }
        : null,
  };
}

/** Only "unproven" changes how MISINFO is shown ("MISINFO (unproven)"), so it is the only basis the display text tells apart. */
function basisFromDisplay(display: string | null | undefined): MisinfoBasis | null {
  return /\(unproven\)/i.test(display ?? "") ? "unproven" : null;
}

export function toSegment(s: RawSegment): Segment {
  return { id: s.segment_id, source: s.source, start: s.start_seconds, end: s.end_seconds, text: s.text };
}

function toSearch(t: RawSearchTrail | null | undefined): ClaimSearch | null {
  if (!t) return null;
  return {
    queries: (t.pubmed_queries ?? [])
      .filter((q) => !q.repeat)
      .map((q) => ({ query: q.query, results: q.results ?? null, failed: Boolean(q.failed) })),
    rounds: (t.pubmed_queries ?? []).map((q) => ({
      round: q.round,
      query: q.query,
      results: q.results ?? null,
      failed: Boolean(q.failed),
      repeat: Boolean(q.repeat),
    })),
    sources: (t.references ?? []).map((r) => ({ name: r.name, publisher: r.publisher ?? "", sites: r.sites ?? [] })),
    libraryUsed: Boolean(t.library?.fired),
    retrieved: t.counts.retrieved ?? null,
    screened: t.counts.screened,
    kept: t.counts.kept,
    roundsUsed: t.budget.rounds_used,
    roundsMax: t.budget.rounds_max,
    budgetExhausted: t.budget.exhausted,
    partial: t.recorded === "queries_only",
  };
}

function combineSearches(claims: Claim[]): ResultModel["search"] {
  const all = claims.map((c) => c.search).filter((s): s is ClaimSearch => s !== null);
  if (all.length === 0) return null;
  const uniq = (xs: string[]) => Array.from(new Set(xs));
  return {
    queries: uniq(all.flatMap((s) => s.queries.map((q) => q.query))),
    sites: uniq(all.flatMap((s) => s.sources.flatMap((r) => (r.sites.length ? r.sites : [r.name])))),
    screened: all.reduce((n, s) => n + s.screened, 0),
    kept: all.reduce((n, s) => n + s.kept, 0),
    ranAt: null,
  };
}

function toClaim(c: RawClaim, number: number): Claim {
  const sources = (c.evidence ?? []).map(toSource);
  const severity = c.severity?.severity;
  const clean = (t: string | null | undefined) => cleanClaimText(displayText(t), sources);
  const quotes = (c.stance_quotes ?? []).map(toSegment);
  return {
    id: c.claim_id,
    number,
    text: c.text,
    start: c.start_seconds,
    end: c.end_seconds,
    deciding: c.deciding,
    stance: isStance(c.stance) ? c.stance : null,
    verdict: isVerdict(c.verdict) ? c.verdict : null,
    verdictExplanation: clean(c.verdict_explanation),
    limitations: (c.limitations ?? []).map(clean),
    stanceRationale: clean(c.stance_rationale),
    quotes,
    speakerQuote: toSpeakerQuote(c.speaker_quote, quotes),
    modality: c.modality ?? null,
    sourceSegmentIds: c.source_segment_ids ?? [],
    sources,
    evidence: summariseEvidence(sources),
    criticNotes: (c.critic?.issues ?? []).map(clean),
    severity: isSeverity(severity) ? severity : null,
    search: toSearch(c.search_trail),
  };
}

/** Text that still names a claim by its internal id ("claim c2") is not shown as is. */
const INTERNAL_CLAIM_REF = /\bclaim [a-z]\d+\b/i;

function toReason(r: RawReason | string, numberOf: (cid: string | null | undefined) => number | null, allSources: NamedSource[] = []): Reason {
  if (typeof r === "string") {
    const parts = r.split(":");
    const cid = parts.length > 1 && /^[a-z]\d+$/i.test(parts[parts.length - 1]) ? parts[parts.length - 1] : null;
    return { code: r, claimNumber: numberOf(cid), text: reasonText(r) };
  }
  const usable = r.text && !INTERNAL_CLAIM_REF.test(r.text) && !/rule '/.test(r.text);
  return {
    code: r.code,
    claimNumber: numberOf(r.claim_id),
    text: usable ? replaceEvidenceIds(displayText(r.text), allSources) : reasonText(r.code),
  };
}

export function adaptResult(raw: RawResult): ResultModel {
  const rawClaims = [...(raw.claims ?? [])].sort(
    (a, b) => a.start_seconds - b.start_seconds || a.claim_id.localeCompare(b.claim_id),
  );
  const claims = rawClaims.map((c, i) => toClaim(c, i + 1));
  const byId = new Map(claims.map((c) => [c.id, c]));
  const numberOf = (cid: string | null | undefined) => (cid ? byId.get(cid)?.number ?? null : null);
  const allSources = claims.flatMap((c) => c.sources);

  const decidingIds = raw.deciding_claim_ids?.length ? raw.deciding_claim_ids : claims.filter((c) => c.deciding).map((c) => c.id);
  const decidingClaims = decidingIds.map((id) => byId.get(id)).filter((c): c is Claim => Boolean(c));

  const review = raw.review ?? null;
  const reasons = review
    ? review.reason_details?.length
      ? review.reason_details.map((r) => toReason(r, numberOf, allSources))
      : review.reasons.map((r) => toReason(r, numberOf, allSources))
    : [];

  const label = isVideoLabel(raw.label) ? raw.label : null;
  const corrected = review?.status === "CORRECTED" && isVideoLabel(review.corrected_label) ? review.corrected_label : null;

  const transcript = [...(raw.transcript_segments ?? []), ...(raw.ocr_segments ?? [])]
    .map(toSegment)
    .sort((a, b) => a.start - b.start || (a.source === "speech" ? -1 : 1));

  return {
    jobId: raw.job_id,
    videoId: raw.video_id ?? null,
    filename: raw.filename ?? "Untitled video",
    label,
    basis: label === "MISINFO" && isMisinfoBasis(raw.misinfo_basis) ? raw.misinfo_basis : null,
    correctedLabel: corrected,
    explanation: replaceEvidenceIds(displayText(raw.explanation), allSources),
    decisionRule: raw.decision_rule ?? null,
    reviewStatus: raw.review === undefined && raw.status === "REVIEW_REQUIRED" ? "PENDING" : toReviewStatus(review),
    reviewDecidedAt: review?.decided_at ?? null,
    reviewSeverity: isSeverity(review?.severity) ? (review?.severity as Severity) : null,
    supersededByJobId: review?.superseded_by_job_id ?? null,
    submittedBy: raw.submitted_by ?? null,
    versions: toVersions(raw),
    reasons,
    claims,
    decidingClaims,
    transcript,
    hasClaimLevel: claims.length > 0,
    submittedAt: raw.submitted_at ?? null,
    analysedAt: raw.created_at ?? null,
    analysisVersion: raw.pipeline_version ?? null,
    search: combineSearches(claims),
  };
}

/** m:ss, for timestamps. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Which claim (if any) covers a moment of the video. A claim covers [start, end):
 * where one claim ends and the next starts, the moment belongs to the next one, so
 * seeking to a claim's start selects that claim. The very end of the last claim
 * still counts as inside it.
 */
export function claimAt(claims: Claim[], t: number): Claim | null {
  return claims.find((c) => t >= c.start && t < c.end) ?? claims.find((c) => t === c.end) ?? null;
}

/** The claims whose source segments include this transcript segment. */
export function claimsForSegment(claims: Claim[], seg: Segment): Claim[] {
  return claims.filter(
    (c) => c.sourceSegmentIds.includes(seg.id) || (c.sourceSegmentIds.length === 0 && seg.start < c.end && seg.end > c.start),
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Text alternative for the evidence strip, e.g. "2 randomised trials against · official guidance against". */
export function evidenceText(e: EvidenceSummary, levelNames: Record<EvidenceLevel, { one: string; many: string }>): string {
  const parts = [
    ...e.levels.map((l) => `${plural(l.count, levelNames[l.level].one, levelNames[l.level].many)} ${l.direction === "supports" ? "for" : "against"}`),
    ...e.guidance.map((g) => `official guidance ${g.direction === "supports" ? "for" : "against"}`),
  ];
  // T65: sources with no strip level are named by the same study type the source list shows.
  for (const o of e.others ?? []) parts.push(`${studyTypeCount(o.studyType, o.count)} ${o.direction === "supports" ? "for" : "against"}`);
  return parts.length === 0 ? "No source found that tests this claim" : parts.join(" · ");
}
