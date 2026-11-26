// ADAPTER: GET /jobs/{job_id}/result → the view model the result page renders.
//
// The page never reads the raw response. Everything that can go wrong with the
// API's values is handled here, once: unknown enums, missing T26/T30/T31 fields,
// internal names in free text, claim ordering and numbering. When the backend
// shape changes, this file changes; the components don't.

import {
  displayText,
  evidenceLevel,
  isMisinfoBasis,
  isStance,
  isVerdict,
  isVideoLabel,
  reasonText,
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
};

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
  modality: "speech" | "screen" | "both" | null;
  sourceSegmentIds: string[];
  sources: Source[];
  evidence: EvidenceSummary;
  criticNotes: string[];
  severity: Severity | null;
  search: ClaimSearch | null;
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
    title: e.title,
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
  };
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
  return {
    supports: directional.filter((s) => s.relation === "SUPPORTS").length,
    contradicts: directional.filter((s) => s.relation === "CONTRADICTS").length,
    levels,
    guidance,
  };
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
  return {
    id: c.claim_id,
    number,
    text: c.text,
    start: c.start_seconds,
    end: c.end_seconds,
    deciding: c.deciding,
    stance: isStance(c.stance) ? c.stance : null,
    verdict: isVerdict(c.verdict) ? c.verdict : null,
    verdictExplanation: displayText(c.verdict_explanation),
    limitations: (c.limitations ?? []).map(displayText),
    stanceRationale: displayText(c.stance_rationale),
    quotes: (c.stance_quotes ?? []).map(toSegment),
    modality: c.modality ?? null,
    sourceSegmentIds: c.source_segment_ids ?? [],
    sources,
    evidence: summariseEvidence(sources),
    criticNotes: (c.critic?.issues ?? []).map(displayText),
    severity: isSeverity(severity) ? severity : null,
    search: toSearch(c.search_trail),
  };
}

/** Text that still names a claim by its internal id ("claim c2") is not shown as is. */
const INTERNAL_CLAIM_REF = /\bclaim [a-z]\d+\b/i;

function toReason(r: RawReason | string, numberOf: (cid: string | null | undefined) => number | null): Reason {
  if (typeof r === "string") {
    const parts = r.split(":");
    const cid = parts.length > 1 && /^[a-z]\d+$/i.test(parts[parts.length - 1]) ? parts[parts.length - 1] : null;
    return { code: r, claimNumber: numberOf(cid), text: reasonText(r) };
  }
  const usable = r.text && !INTERNAL_CLAIM_REF.test(r.text) && !/rule '/.test(r.text);
  return {
    code: r.code,
    claimNumber: numberOf(r.claim_id),
    text: usable ? displayText(r.text) : reasonText(r.code),
  };
}

export function adaptResult(raw: RawResult): ResultModel {
  const rawClaims = [...(raw.claims ?? [])].sort(
    (a, b) => a.start_seconds - b.start_seconds || a.claim_id.localeCompare(b.claim_id),
  );
  const claims = rawClaims.map((c, i) => toClaim(c, i + 1));
  const byId = new Map(claims.map((c) => [c.id, c]));
  const numberOf = (cid: string | null | undefined) => (cid ? byId.get(cid)?.number ?? null : null);

  const decidingIds = raw.deciding_claim_ids?.length ? raw.deciding_claim_ids : claims.filter((c) => c.deciding).map((c) => c.id);
  const decidingClaims = decidingIds.map((id) => byId.get(id)).filter((c): c is Claim => Boolean(c));

  const review = raw.review ?? null;
  const reasons = review
    ? review.reason_details?.length
      ? review.reason_details.map((r) => toReason(r, numberOf))
      : review.reasons.map((r) => toReason(r, numberOf))
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
    explanation: displayText(raw.explanation),
    decisionRule: raw.decision_rule ?? null,
    reviewStatus: raw.review === undefined && raw.status === "REVIEW_REQUIRED" ? "PENDING" : toReviewStatus(review),
    reviewDecidedAt: review?.decided_at ?? null,
    reviewSeverity: isSeverity(review?.severity) ? (review?.severity as Severity) : null,
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
  if (parts.length === 0) {
    const n = e.supports + e.contradicts;
    return n === 0 ? "No source found that tests this claim" : `${plural(n, "source", "sources")} without a study type`;
  }
  return parts.join(" · ");
}
