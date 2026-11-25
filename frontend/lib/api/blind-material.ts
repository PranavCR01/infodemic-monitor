// T40: GET /v1/reviews/{id}/blind-material, what a blind reviewer judges from.
// The server leaves out everything the system concluded: no relation (supports /
// contradicts), verdict, stance, citation or deciding marker, score or reasons.
// Papers come in retrieval (rerank) order, and the frontend keeps that order: it
// never re-sorts them by study strength, which would be a reading of its own.
import { apiFetch } from "@/lib/api";
import { evidenceLevel } from "@/lib/vocabulary";
import { toSegment, type Segment, type Source, type SourceKind } from "./result-adapter";
import type { RawSegment } from "./result-types";

export type RawBlindReference = {
  evidence_id: string;
  source_kind: SourceKind;
  rank: number;
  title: string;
  year?: number | null;
  publisher?: string | null;
  study_type?: string | null;
  abstract_snippet?: string;
  url?: string | null;
  pmid?: string | null;
  doi?: string | null;
};

export type RawBlindClaim = {
  claim_id: string;
  text?: string | null;
  category?: string | null;
  start_seconds?: number | null;
  end_seconds?: number | null;
  source_segment_ids?: string[];
  references?: RawBlindReference[];
};

export type RawBlindMaterial = {
  review_id: string;
  job_id: string;
  video_id?: string | null;
  material: "blind";
  claims?: RawBlindClaim[];
  transcript_segments?: RawSegment[];
  ocr_segments?: RawSegment[];
};

/** A source as the blind step shows it. `relation` is never known here. */
export type BlindSource = Omit<Source, "relation">;

export type BlindClaimMaterial = {
  id: string;
  /** What the speaker said or showed for this claim, as the extractor quoted it. */
  quotes: Segment[];
  /** In retrieval order. */
  sources: BlindSource[];
};

export type BlindMaterial = { claims: Record<string, BlindClaimMaterial> };

function toBlindSource(r: RawBlindReference): BlindSource {
  const kind = r.source_kind;
  return {
    id: r.evidence_id,
    title: r.title,
    studyType: r.study_type ?? null,
    level: evidenceLevel(r.study_type),
    kind,
    year: r.year ?? null,
    publisher: r.publisher ?? null,
    snippet: r.abstract_snippet ?? "",
    // Internal library documents never get an external link (HANDOFF §4 SourceCard).
    url: kind === "library" ? null : r.url ?? (r.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/` : null),
    pmid: r.pmid ?? null,
  };
}

export function adaptBlindMaterial(raw: RawBlindMaterial): BlindMaterial {
  const segs = [...(raw.transcript_segments ?? []), ...(raw.ocr_segments ?? [])].map(toSegment);
  const byId = new Map(segs.map((s) => [s.id, s]));
  const claims: Record<string, BlindClaimMaterial> = {};
  for (const c of raw.claims ?? []) {
    claims[c.claim_id] = {
      id: c.claim_id,
      quotes: (c.source_segment_ids ?? []).map((id) => byId.get(id)).filter((s): s is Segment => Boolean(s)),
      sources: [...(c.references ?? [])].sort((a, b) => a.rank - b.rank).map(toBlindSource),
    };
  }
  return { claims };
}

export type BlindMaterialLoad = { kind: "ok"; material: BlindMaterial } | { kind: "not_blind" } | { kind: "error" };

/** 403 BLIND_STEP_NOT_ACTIVE: the caller isn't blind on this case (any more); use the case and result. */
export async function fetchBlindMaterial(reviewId: string): Promise<BlindMaterialLoad> {
  try {
    const res = await apiFetch(`/v1/reviews/${encodeURIComponent(reviewId)}/blind-material`);
    if (res.ok) return { kind: "ok", material: adaptBlindMaterial((await res.json()) as RawBlindMaterial) };
    if (res.status === 403) {
      const body = (await res.json().catch(() => null)) as { detail?: { code?: string } } | null;
      if (body?.detail?.code === "BLIND_STEP_NOT_ACTIVE") return { kind: "not_blind" };
    }
    return { kind: "error" };
  } catch {
    return { kind: "error" };
  }
}
