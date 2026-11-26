// T65 fixture: the problems seen in the exported report of the vitamin K re-analysis
// (production job d2bf4179), on invented data. ev_ ids in model text, "the reviewer" for
// the second automated check, titles ending in a full stop, study types without a strip
// level, a best-overlap speaker quote, and journal / publication date (new, optional).
import type { RawResult } from "../result-types";

export const MOCK_T65: RawResult = {
  job_id: "mock-job-t65",
  video_id: "mock-video-t65",
  filename: "vitamin-k-shot.mp4",
  status: "REVIEW_REQUIRED",
  label: "MISINFO",
  misinfo_basis: "contradicted",
  confidence: 0.7,
  explanation: "The speaker says the newborn vitamin K shot is unnecessary; ev_k1 and ev_k2 report bleeding cases in infants who did not get it.",
  created_at: "2026-11-26T10:00:00Z",
  pipeline_version: "graph_v1+91a7a13+p1a2b3c4d",
  decision_rule: "endorsed_contradicted",
  deciding_claim_ids: ["c1"],
  transcript_segments: [
    { segment_id: "t1", source: "speech", start_seconds: 0, end_seconds: 4, text: "Hi everyone, welcome back." },
    { segment_id: "t2", source: "speech", start_seconds: 4, end_seconds: 9, text: "A JAMA study published November 5th showed the vitamin K shot is unnecessary." },
  ],
  ocr_segments: [],
  review: {
    status: "REVIEW_REQUIRED",
    reasons: ["weak_evidence:c1"],
    case_status: "OPEN",
    reason_details: [{ code: "weak_evidence", rule: "weak_evidence", claim_id: "c1", text: "The evidence (ev_k3) is too weak to decide.", raw: "weak_evidence:c1" }],
  },
  claims: [
    {
      claim_id: "c1",
      text: "The newborn vitamin K shot is unnecessary.",
      category: "treatment_efficacy",
      start_seconds: 0,
      end_seconds: 9,
      deciding: true,
      stance: "ENDORSES",
      verdict: "CONTRADICTED",
      verdict_explanation: "The case report [ev_k1] and the narrative review ev_k2 describe late bleeding without the shot. The reviewer noted the review is old; ev_unknown was also cited.",
      limitations: ["The reviewer's note: no randomised trial (ev_k3)."],
      stance_rationale: "Stated as fact.",
      // The first stance segment is the greeting: the old quote. speaker_quote carries the claim.
      stance_quotes: [
        { segment_id: "t1", source: "speech", start_seconds: 0, end_seconds: 4, text: "Hi everyone, welcome back." },
        { segment_id: "t2", source: "speech", start_seconds: 4, end_seconds: 9, text: "A JAMA study published November 5th showed the vitamin K shot is unnecessary." },
      ],
      speaker_quote: "A JAMA study published November 5th showed the vitamin K shot is unnecessary.",
      critic: { decision: "ACCEPT", issues: ["The reviewer would like a trial; ev_k1 is a single case."] },
      evidence: [
        {
          evidence_id: "ev_k1",
          title: "Late vitamin K deficiency bleeding in an infant whose parents declined prophylaxis: a case report.",
          pmid: "00000101",
          relation: "CONTRADICTS",
          study_type: "case_report",
          source_kind: "pubmed",
          year: 2021,
          publisher: "[Journal]",
          journal: "J Pediatr",
          pub_date: "2021-03-05",
        },
        {
          evidence_id: "ev_k2",
          title: "Vitamin K prophylaxis in newborns: a narrative review.",
          pmid: "00000102",
          relation: "CONTRADICTS",
          study_type: "narrative_review",
          source_kind: "pubmed",
          year: 2016,
          publisher: "[Journal]",
          journal: "Pediatrics",
          pub_date: "2016-11",
        },
        {
          evidence_id: "ev_k3",
          title: "",
          pmid: "00000103",
          relation: "CONTRADICTS",
          study_type: "case_report",
          source_kind: "pubmed",
          year: 2019,
          publisher: null,
          journal: null,
          pub_date: null,
        },
      ],
    },
  ],
};

/** An older result: no journal, pub_date or speaker_quote anywhere. */
export const MOCK_T65_OLD: RawResult = {
  ...MOCK_T65,
  claims: MOCK_T65.claims!.map((c) => ({
    ...c,
    speaker_quote: undefined,
    evidence: c.evidence!.map(({ journal: _j, pub_date: _p, ...e }) => e),
  })),
};
