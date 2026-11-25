// MOCK DATA for the review screens, in the shape of T27 + T33 + T34 (reviews.py).
// Invented; used by /dev/review and tests only.
import type { RawCase, RawCaseClaim, RawPreReveal, RawQueueItem } from "../review-types";

const H = 3600;

/** The signed-in user in /dev/review and tests. `submitted_by` is a Supabase user id since T33. */
export const MOCK_VIEWER_ID = "5d1e9b40-2c7a-4f3e-9a61-0b8f3c2d7e15";
const OTHER_A = "a83f02c6-71d4-4b9e-8f20-6c5e1d9a3b74";
const OTHER_B = "c2b7e4d9-0f16-4a8c-b3e5-92d1f7a06c38";

/** rev-1's system view: what T34 withholds until the reviewer has given their own judgement. */
const REV1_SYSTEM = {
  reasons: ["weak_evidence:c3", "judge:false_claim_not_refuted:c1"],
  proposed_label: "MISINFO",
  rules_fired: [] as Record<string, unknown>[],
};

// rev-1's claims, as the case lists them (same ids and text as MOCK_MISINFO_PENDING).
const REV1_CLAIMS: RawCaseClaim[] = [
  { claim_id: "c1", text: "Drinking hot water every hour cures the flu in two days.", start: 3.2, end: 7.9, severity: "HIGH", stance: "ENDORSES", verdict: "CONTRADICTED" },
  { claim_id: "c2", text: "Flu vaccines don't work for people under fifty.", start: 8.1, end: 12.4, severity: "MEDIUM", stance: "QUOTES", verdict: "CONTRADICTED" },
  { claim_id: "c3", text: "High-dose vitamin C prevents viral infections.", start: 13.5, end: 18.0, severity: "LOW", stance: "ENDORSES", verdict: "INSUFFICIENT_EVIDENCE" },
];
const withheld = (c: RawCaseClaim): RawCaseClaim => ({ ...c, stance: null, verdict: null });

export const MOCK_QUEUE: RawQueueItem[] = [
  {
    // HIGH, and this reviewer hasn't judged it yet: the system's view is withheld.
    review_id: "rev-1", job_id: "mock-job-1", filename: "hot-water-flu.mp4", status: "OPEN", severity: "HIGH",
    reasons: [], rules_fired: [], proposed_label: null, blind_step_required: true, system_view_withheld: true,
    created_at: "2026-11-23T09:13:16Z", age_seconds: 5 * H, submitted_by: OTHER_A, submitted_by_name: "Dr. A. Mensah", is_own: false,
  },
  {
    // HIGH, already judged by this reviewer: shown in full.
    review_id: "rev-3", job_id: "mock-job-3", filename: "sea-moss-thyroid.mp4", status: "OPEN", severity: "HIGH",
    reasons: ["unproven_claim:c1"], proposed_label: "MISINFO", blind_step_required: true, system_view_withheld: false,
    created_at: "2026-11-23T11:00:00Z", age_seconds: 2 * H, submitted_by: OTHER_B, submitted_by_name: "J. Okafor", is_own: false,
  },
  {
    review_id: "rev-4", job_id: "mock-job-4", filename: "lemon-detox.mp4", status: "OPEN", severity: "MEDIUM",
    reasons: ["judge:possible_debunk:c1", "weak_evidence:c1"], proposed_label: "CANNOT_RECOGNIZE",
    created_at: "2026-11-22T08:00:00Z", age_seconds: 30 * H, submitted_by: MOCK_VIEWER_ID, submitted_by_name: "You (mock)", is_own: true,
  },
  {
    review_id: "rev-5", job_id: "mock-job-6", filename: "ginger-tea-colds.mp4", status: "OPEN", severity: "LOW",
    reasons: ["unclear_stance:c2", "nothing_judged"], proposed_label: "NO_MISINFO",
    created_at: "2026-11-21T08:00:00Z", age_seconds: 60 * H, submitted_by: OTHER_A, submitted_by_name: "Dr. A. Mensah", is_own: false,
  },
];

const REV1_AUDIT = [
  { id: "a1", actor_id: "system", action: "review_opened", entity_type: "review", entity_id: "rev-1", created_at: "2026-11-23T09:13:16Z", actor_name: "System" },
];

/** rev-1 before this reviewer's judgement: claims to judge, nothing of the system's. */
export const MOCK_CASE_HIGH: RawCase = { ...MOCK_QUEUE[0], claims: REV1_CLAIMS.map(withheld), pre_reveal: null, audit_trail: REV1_AUDIT };

/** What POST /pre-reveal answers: the same case, revealed, with the reviewer's judgement. */
export function mockRevealed(mine: { claim_id: string; stance: string; verdict: string }[]): RawCase {
  const pre: RawPreReveal = {
    id: "pre-1", reviewer_id: MOCK_VIEWER_ID, case_severity: "HIGH", created_at: "2026-11-23T14:00:00Z",
    claims: Object.fromEntries(mine.map((m) => [m.claim_id, { stance: m.stance, verdict: m.verdict }])),
  };
  return { ...MOCK_CASE_HIGH, ...REV1_SYSTEM, system_view_withheld: false, claims: REV1_CLAIMS, pre_reveal: pre };
}

/** rev-1 as a MEDIUM case: no blind step, the system's view straight away. */
export const MOCK_CASE_NORMAL: RawCase = {
  ...MOCK_CASE_HIGH, ...REV1_SYSTEM, severity: "MEDIUM", blind_step_required: false, system_view_withheld: false, claims: REV1_CLAIMS,
};

export const MOCK_CASE_DECIDED: RawCase = {
  ...MOCK_QUEUE[1],
  status: "RESOLVED",
  blind_step_required: false, // only open cases need the blind step
  decision: { reviewer_id: "7f3c2a11-0000", reviewer_name: "Dr. B. Osei", action: "APPROVE", reason_code: "SYSTEM_CORRECT", reason: "No study supports sea moss for thyroid disease.", decided_at: "2026-11-23T12:30:00Z" },
  audit_trail: [
    { id: "a2", actor_id: "7f3c2a11-0000", actor_name: "Dr. B. Osei", action: "APPROVE", entity_type: "review", entity_id: "rev-3", reason: "No study supports sea moss for thyroid disease.", created_at: "2026-11-23T12:30:00Z" },
  ],
};

export const MOCK_CASE_OWN: RawCase = { ...MOCK_QUEUE[2], audit_trail: [] };
