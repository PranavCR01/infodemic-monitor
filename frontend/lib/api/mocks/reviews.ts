// MOCK DATA for the review screens, in the shape of T27 (#78) plus its PROPOSED fields.
// Invented; used by /dev/review and tests only.
import type { RawCase, RawQueueItem } from "../review-types";

const H = 3600;

export const MOCK_QUEUE: RawQueueItem[] = [
  {
    review_id: "rev-1", job_id: "mock-job-1", filename: "hot-water-flu.mp4", status: "OPEN", severity: "HIGH",
    reasons: ["weak_evidence:c3", "judge:false_claim_not_refuted:c1"], proposed_label: "MISINFO",
    created_at: "2026-11-23T09:13:16Z", age_seconds: 5 * H, submitted_by: "a.mensah@who-research.org", is_own: false,
  },
  {
    review_id: "rev-3", job_id: "mock-job-3", filename: "sea-moss-thyroid.mp4", status: "OPEN", severity: "HIGH",
    reasons: ["unproven_claim:c1"], proposed_label: "MISINFO",
    created_at: "2026-11-23T11:00:00Z", age_seconds: 2 * H, submitted_by: "j.okafor@who-research.org", is_own: false,
  },
  {
    review_id: "rev-4", job_id: "mock-job-4", filename: "lemon-detox.mp4", status: "OPEN", severity: "MEDIUM",
    reasons: ["judge:possible_debunk:c1", "weak_evidence:c1"], proposed_label: "CANNOT_RECOGNIZE",
    created_at: "2026-11-22T08:00:00Z", age_seconds: 30 * H, submitted_by: "you@who-research.org", is_own: true,
  },
  {
    review_id: "rev-5", job_id: "mock-job-6", filename: "ginger-tea-colds.mp4", status: "OPEN", severity: "LOW",
    reasons: ["unclear_stance:c2"], proposed_label: "NO_MISINFO",
    created_at: "2026-11-21T08:00:00Z", age_seconds: 60 * H, submitted_by: "a.mensah@who-research.org", is_own: false,
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
