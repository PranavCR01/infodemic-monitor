// MOCK DATA for the review screens, in the shape of T27 (#78) + T33 (#94) plus T34's PROPOSED names.
// Invented; used by /dev/review and tests only.
import type { RawCase, RawQueueItem } from "../review-types";

const H = 3600;

/** The signed-in user in /dev/review and tests. `submitted_by` is a Supabase user id since T33. */
export const MOCK_VIEWER_ID = "5d1e9b40-2c7a-4f3e-9a61-0b8f3c2d7e15";
const OTHER_A = "a83f02c6-71d4-4b9e-8f20-6c5e1d9a3b74";
const OTHER_B = "c2b7e4d9-0f16-4a8c-b3e5-92d1f7a06c38";

export const MOCK_QUEUE: RawQueueItem[] = [
  {
    review_id: "rev-1", job_id: "mock-job-1", filename: "hot-water-flu.mp4", status: "OPEN", severity: "HIGH",
    reasons: ["weak_evidence:c3", "judge:false_claim_not_refuted:c1"], proposed_label: "MISINFO",
    created_at: "2026-11-23T09:13:16Z", age_seconds: 5 * H, submitted_by: OTHER_A,
  },
  {
    review_id: "rev-3", job_id: "mock-job-3", filename: "sea-moss-thyroid.mp4", status: "OPEN", severity: "HIGH",
    reasons: ["unproven_claim:c1"], proposed_label: "MISINFO",
    created_at: "2026-11-23T11:00:00Z", age_seconds: 2 * H, submitted_by: OTHER_B,
  },
  {
    review_id: "rev-4", job_id: "mock-job-4", filename: "lemon-detox.mp4", status: "OPEN", severity: "MEDIUM",
    reasons: ["judge:possible_debunk:c1", "weak_evidence:c1"], proposed_label: "CANNOT_RECOGNIZE",
    created_at: "2026-11-22T08:00:00Z", age_seconds: 30 * H, submitted_by: MOCK_VIEWER_ID,
  },
  {
    review_id: "rev-5", job_id: "mock-job-6", filename: "ginger-tea-colds.mp4", status: "OPEN", severity: "LOW",
    reasons: ["unclear_stance:c2"], proposed_label: "NO_MISINFO",
    created_at: "2026-11-21T08:00:00Z", age_seconds: 60 * H, submitted_by: OTHER_A,
  },
];

export const MOCK_CASE_HIGH: RawCase = {
  ...MOCK_QUEUE[0],
  audit_trail: [
    { id: "a1", actor_id: "system", action: "review_opened", entity_type: "review", entity_id: "rev-1", created_at: "2026-11-23T09:13:16Z", actor_name: "System" },
  ],
};

export const MOCK_CASE_DECIDED: RawCase = {
  ...MOCK_QUEUE[1],
  status: "RESOLVED",
  decision: { reviewer_id: "7f3c2a11-0000", reviewer_name: "Dr. B. Osei", action: "APPROVE", reason: "[SYSTEM_CORRECT] No study supports sea moss for thyroid disease.", decided_at: "2026-11-23T12:30:00Z" },
  audit_trail: [
    { id: "a2", actor_id: "7f3c2a11-0000", actor_name: "Dr. B. Osei", action: "APPROVE", entity_type: "review", entity_id: "rev-3", reason: "[SYSTEM_CORRECT] No study supports sea moss for thyroid disease.", created_at: "2026-11-23T12:30:00Z" },
  ],
};

export const MOCK_CASE_OWN: RawCase = { ...MOCK_QUEUE[2], audit_trail: [] };
