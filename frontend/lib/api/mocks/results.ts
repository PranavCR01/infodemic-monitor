// MOCK DATA for the result page while T26 / T30 / T31 are not merged.
// Invented examples in the shape of backend/app/api/result_models.py (auto/T26).
// Titles, quotes and passages are placeholders, not real citations.
// Used by /dev/result and by tests only. The real page always calls the API.

import type { RawResult, RawSegment } from "../result-types";

const seg = (id: string, source: "speech" | "screen", start: number, end: number, text: string): RawSegment => ({
  segment_id: id,
  source,
  start_seconds: start,
  end_seconds: end,
  text,
});

const transcript = [
  seg("t1", "speech", 0, 3.2, "Okay, so everyone keeps asking me what I do when I feel a cold coming on."),
  seg("t2", "speech", 3.2, 8.1, "Drinking hot water every hour cures the flu in two days. That's it, that's the secret."),
  seg("t3", "speech", 8.1, 13.5, "My doctor told me flu shots don't work for people under fifty anyway."),
  seg("t4", "speech", 13.5, 19.0, "And honestly, vitamin C megadoses wipe out any virus before it starts."),
  seg("t5", "speech", 19.0, 23.0, "Try it and tell me how it goes."),
];
const ocr = [seg("o1", "screen", 3.5, 8.0, "HOT WATER = NO MORE FLU"), seg("o2", "screen", 13.6, 18.5, "1000mg VIT C x5 A DAY")];

/** MISINFO, waiting for review (the design's main example). */
export const MOCK_MISINFO_PENDING: RawResult = {
  job_id: "mock-job-1",
  video_id: "mock-video-1",
  filename: "hot-water-flu.mp4",
  status: "REVIEW_REQUIRED",
  label: "MISINFO",
  misinfo_basis: "contradicted",
  confidence: 0.82,
  explanation:
    "The speaker presents drinking hot water as a cure for flu. A randomised trial and WHO guidance found no effect of hot drinks on how long flu lasts.",
  submitted_at: "2026-11-23T09:12:00Z",
  created_at: "2026-11-23T09:13:16Z",
  pipeline: "graph",
  decision_rule: "endorsed_contradicted",
  deciding_claim_ids: ["c1"],
  transcript_segments: transcript,
  ocr_segments: ocr,
  review: {
    status: "REVIEW_REQUIRED",
    reasons: ["weak_evidence:c3", "judge:false_claim_not_refuted:c1"],
    review_id: "rev-1",
    case_status: "OPEN",
    resolved: false,
    severity: "HIGH",
    reason_details: [
      { code: "weak_evidence", rule: "weak_evidence", claim_id: "c3", text: "The evidence for claim c3 is too weak or too mixed to decide.", raw: "weak_evidence:c3" },
      { code: "false_claim_not_refuted", rule: "judge_flags", claim_id: "c1", text: "Claim c1 is contradicted by the evidence but is repeated without being refuted.", raw: "judge:false_claim_not_refuted:c1" },
    ],
  },
  claims: [
    {
      claim_id: "c1",
      id: "row-c1",
      text: "Drinking hot water every hour cures the flu in two days.",
      category: "treatment_efficacy",
      start_seconds: 3.2,
      end_seconds: 8.1,
      deciding: true,
      label: "MISINFO",
      stance: "ENDORSES",
      verdict: "CONTRADICTED",
      verdict_explanation: "A randomised trial found hot drinks eased symptoms briefly but did not shorten the illness. WHO guidance lists no drink as a flu cure.",
      limitations: ["Indirect outcome: the trial measured symptom relief, not illness duration."],
      modality: "both",
      source_segment_ids: ["t2", "o1"],
      stance_rationale: "The speaker states the claim as fact, in their own voice, and calls it 'the secret'.",
      stance_quotes: [transcript[1], ocr[0]],
      critic: { decision: "ACCEPT", issues: ["The trial population was adults with common cold, not confirmed influenza."] },
      severity: { claim_id: "c1", severity: "HIGH" },
      evidence: [
        { evidence_id: "e1", title: "[Placeholder] Hot drinks and symptom relief in upper respiratory infection: a randomised trial", pmid: "00000001", relation: "CONTRADICTS", study_type: "rct", source_kind: "pubmed", year: 2019, publisher: "[Journal]", abstract_snippet: "[Placeholder passage] Hot drinks improved subjective symptoms for 15 minutes; illness duration did not differ between groups." },
        { evidence_id: "e2", title: "[Placeholder] WHO: Influenza (seasonal) fact sheet", url: "https://www.who.int/", relation: "CONTRADICTS", study_type: "guideline", source_kind: "reference", year: 2023, publisher: "World Health Organization", abstract_snippet: "[Placeholder passage] Treatment is aimed at relieving symptoms; antivirals may be used for people at higher risk." },
      ],
    },
    {
      claim_id: "c2",
      id: "row-c2",
      text: "Flu vaccines don't work for people under fifty.",
      category: "prevention",
      start_seconds: 8.1,
      end_seconds: 13.5,
      deciding: false,
      stance: "QUOTES",
      verdict: "CONTRADICTED",
      verdict_explanation: "A systematic review found flu vaccination reduces confirmed influenza in healthy adults of working age.",
      limitations: [],
      modality: "speech",
      source_segment_ids: ["t3"],
      stance_rationale: "The speaker reports what their doctor said rather than stating it themselves.",
      stance_quotes: [transcript[2]],
      evidence: [
        { evidence_id: "e3", title: "[Placeholder] Vaccines for preventing influenza in healthy adults: a systematic review", pmid: "00000002", relation: "CONTRADICTS", study_type: "systematic_review", source_kind: "pubmed", year: 2018, publisher: "[Journal]", abstract_snippet: "[Placeholder passage] Vaccination reduced confirmed influenza from 2.3% to 0.9%." },
      ],
    },
    {
      claim_id: "c3",
      id: "row-c3",
      text: "High-dose vitamin C prevents viral infections.",
      category: "prevention",
      start_seconds: 13.5,
      end_seconds: 19.0,
      deciding: false,
      stance: "ENDORSES",
      verdict: "INSUFFICIENT_EVIDENCE",
      verdict_explanation: "Studies of vitamin C and colds point in different directions and none test 'any virus'. No study settles a claim this broad.",
      limitations: ["Claim is broader than any study: 'any virus'."],
      modality: "both",
      source_segment_ids: ["t4", "o2"],
      stance_rationale: "Stated as fact by the speaker.",
      stance_quotes: [transcript[3], ocr[1]],
      evidence: [],
    },
  ],
  search: {
    pubmed_queries: ["(hot water OR hot drinks) AND (influenza OR flu) AND (duration OR recovery)", "influenza vaccine efficacy adults"],
    reference_sites: ["who.int", "cdc.gov", "nhs.uk"],
    results_screened: 14,
    results_kept: 3,
    ran_at: "2026-11-23T09:13:00Z",
  },
};

/** DEBUNKED, verified by a reviewer. */
export const MOCK_DEBUNKED_VERIFIED: RawResult = {
  job_id: "mock-job-2",
  video_id: "mock-video-2",
  filename: "pharmacist-explains-garlic.mov",
  status: "SUCCESS",
  label: "DEBUNKING",
  confidence: 0.77,
  explanation:
    "The pharmacist names the claim that garlic cures high blood pressure and says it is wrong. A systematic review found garlic does not replace treatment.",
  submitted_at: "2026-11-22T15:01:00Z",
  pipeline: "graph",
  decision_rule: "refuted_contradicted",
  deciding_claim_ids: ["c1"],
  transcript_segments: [
    seg("t1", "speech", 0, 4.0, "You've probably seen people saying garlic cures high blood pressure."),
    seg("t2", "speech", 4.0, 9.5, "It doesn't. Please don't stop your medication for it."),
  ],
  ocr_segments: [],
  review: {
    status: "VERIFIED",
    reasons: ["judge:possible_debunk:c1"],
    review_id: "rev-2",
    case_status: "RESOLVED",
    resolved: true,
    action: "APPROVE",
    decided_at: "2026-11-22T16:40:00Z",
    severity: "MEDIUM",
    reason_details: [],
  },
  claims: [
    {
      claim_id: "c1",
      text: "Garlic cures high blood pressure.",
      category: "treatment_efficacy",
      start_seconds: 0,
      end_seconds: 9.5,
      deciding: true,
      stance: "REFUTES",
      verdict: "CONTRADICTED",
      verdict_explanation: "A systematic review found a small effect of garlic supplements on blood pressure, not a cure.",
      limitations: [],
      modality: "speech",
      source_segment_ids: ["t1", "t2"],
      stance_rationale: "The speaker names the claim and says 'It doesn't'.",
      stance_quotes: [seg("t2", "speech", 4.0, 9.5, "It doesn't. Please don't stop your medication for it.")],
      evidence: [
        { evidence_id: "e1", title: "[Placeholder] Garlic for hypertension: a systematic review", pmid: "00000003", relation: "CONTRADICTS", study_type: "systematic_review", source_kind: "pubmed", year: 2020, abstract_snippet: "[Placeholder passage]" },
      ],
    },
  ],
};

/** MISINFO (unproven), decision D1 = B. */
export const MOCK_UNPROVEN: RawResult = {
  job_id: "mock-job-3",
  filename: "sea-moss-thyroid.mp4",
  status: "REVIEW_REQUIRED",
  label: "MISINFO",
  misinfo_basis: "unproven",
  confidence: 0.6,
  explanation: "The speaker says sea moss cures thyroid disease. No study or official source found supports this.",
  decision_rule: "unproven",
  deciding_claim_ids: ["c1"],
  transcript_segments: [seg("t1", "speech", 0, 6, "Sea moss healed my thyroid. Ditch the pills, this is all you need.")],
  review: {
    status: "REVIEW_REQUIRED",
    reasons: ["unproven_claim:c1"],
    review_id: "rev-3",
    case_status: "OPEN",
    resolved: false,
    severity: "HIGH",
    reason_details: [{ code: "unproven_claim", rule: "weak_evidence", claim_id: "c1", text: "", raw: "unproven_claim:c1" }],
  },
  claims: [
    {
      claim_id: "c1",
      text: "Sea moss cures thyroid disease.",
      category: "treatment_efficacy",
      start_seconds: 0,
      end_seconds: 6,
      deciding: true,
      stance: "ENDORSES",
      verdict: "UNSUPPORTED",
      verdict_explanation: "No study or official source found tests sea moss for thyroid disease. No evidence supports this claim.",
      limitations: ["Absence of evidence: the search found nothing either way."],
      modality: "speech",
      source_segment_ids: ["t1"],
      stance_rationale: "Stated as the speaker's own experience and advice.",
      stance_quotes: [seg("t1", "speech", 0, 6, "Sea moss healed my thyroid. Ditch the pills, this is all you need.")],
      evidence: [],
    },
  ],
};

/** CANNOT RECOGNIZE: nothing to check. Today's backend writes an enum prefix into the explanation. */
export const MOCK_NO_CLAIMS: RawResult = {
  job_id: "mock-job-4",
  filename: "morning-stretch.mp4",
  status: "SUCCESS",
  label: "CANNOT_RECOGNIZE",
  confidence: 0.5,
  explanation: "CANNOT_RECOGNIZE: no checkable health claims were found in the video.",
  decision_rule: "no_claims",
  review: null,
  claims: [],
  transcript_segments: [seg("t1", "speech", 0, 5, "Good morning! Let's start with ten slow neck rolls.")],
};

/** Today's API: a single-call result, no claim-level data and no T26 fields. */
export const MOCK_LEGACY: RawResult = {
  job_id: "mock-job-5",
  filename: "legacy-result.mp4",
  label: "NO_MISINFO",
  confidence: 0.9,
  explanation: "The video gives standard hand-washing advice consistent with WHO guidance.",
  review: null,
};

export const MOCK_RESULTS: Record<string, RawResult> = {
  pending: MOCK_MISINFO_PENDING,
  debunked: MOCK_DEBUNKED_VERIFIED,
  unproven: MOCK_UNPROVEN,
  "no-claims": MOCK_NO_CLAIMS,
  legacy: MOCK_LEGACY,
};
