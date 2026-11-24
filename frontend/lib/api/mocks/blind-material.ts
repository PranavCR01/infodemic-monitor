// MOCK DATA: T40's blind material for rev-1, built from MOCK_MISINFO_PENDING by keeping
// only what the server sends (no relation, verdict, stance or deciding marker).
// Invented; used by /dev/review and tests only.
import type { RawBlindMaterial } from "../blind-material";
import { MOCK_MISINFO_PENDING } from "./results";

const r = MOCK_MISINFO_PENDING;

export const MOCK_BLIND_MATERIAL: RawBlindMaterial = {
  review_id: "rev-1",
  job_id: "mock-job-1",
  video_id: r.video_id ?? null,
  material: "blind",
  claims: (r.claims ?? []).map((c) => ({
    claim_id: c.claim_id,
    text: c.text,
    start_seconds: c.start_seconds,
    end_seconds: c.end_seconds,
    source_segment_ids: c.source_segment_ids ?? [],
    // Retrieval order, reversed from the result mock so a test can tell the order is the server's.
    references: [...(c.evidence ?? [])].reverse().map((e, i) => ({
      evidence_id: e.evidence_id,
      source_kind: e.source_kind ?? "other",
      rank: i + 1,
      title: e.title,
      year: e.year ?? null,
      publisher: e.publisher ?? null,
      study_type: e.study_type ?? null,
      abstract_snippet: e.abstract_snippet ?? "",
      url: e.url ?? null,
      pmid: e.pmid ?? null,
      doi: e.doi ?? null,
    })),
  })),
  transcript_segments: r.transcript_segments ?? [],
  ocr_segments: r.ocr_segments ?? [],
};
