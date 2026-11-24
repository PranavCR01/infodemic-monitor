import { describe, expect, it } from "vitest";
import { adaptCase, adaptQueueItem, reasonCounts, sortQueue, waitingText } from "./review-adapter";
import { MOCK_CASE_DECIDED, MOCK_QUEUE, MOCK_VIEWER_ID } from "./mocks/reviews";

describe("review adapter", () => {
  it("reads a queue item into display values", () => {
    const q = adaptQueueItem(MOCK_QUEUE[0]);
    expect(q.severity).toBe("HIGH");
    expect(q.proposedLabel).toBe("MISINFO");
    expect(q.waiting).toBe("5 h");
    expect(q.reasons.map((r) => r.rule)).toEqual(["weak_evidence", "false_claim_not_refuted"]);
    for (const r of q.reasons) expect(r.text).not.toMatch(/_|:c\d/);
  });

  it("collapses the same rule raised by several claims into one chip", () => {
    const q = adaptQueueItem({ ...MOCK_QUEUE[0], reasons: ["weak_evidence:c1", "weak_evidence:c2"] });
    expect(q.reasons).toHaveLength(1);
  });

  it("sorts by severity, then oldest first", () => {
    const items = sortQueue([...MOCK_QUEUE].reverse().map((i) => adaptQueueItem(i)));
    expect(items.map((i) => i.reviewId)).toEqual(["rev-1", "rev-3", "rev-4", "rev-5"]);
  });

  it("puts cases with no severity last", () => {
    const items = sortQueue([adaptQueueItem({ ...MOCK_QUEUE[3], severity: null, age_seconds: 999999 }), adaptQueueItem(MOCK_QUEUE[3])]);
    expect(items[0].severity).toBe("LOW");
  });

  it("counts reasons for the filter buttons", () => {
    const counts = reasonCounts(MOCK_QUEUE.map((i) => adaptQueueItem(i)));
    expect(counts.find((c) => c.rule === "weak_evidence")?.count).toBe(2);
  });

  it("marks the viewer's own submission from T33's submitted_by, and never shows a raw user id", () => {
    const own = adaptQueueItem(MOCK_QUEUE[2], MOCK_VIEWER_ID);
    expect(own).toMatchObject({ isOwn: true, submittedBy: "You" });
    const other = adaptQueueItem(MOCK_QUEUE[0], MOCK_VIEWER_ID);
    expect(other.isOwn).toBe(false);
    expect(other.submittedBy).toBe("User a83f02");
    expect(adaptQueueItem({ ...MOCK_QUEUE[0], submitted_by: null }, MOCK_VIEWER_ID).submittedBy).toBeNull();
  });

  it("is never 'own' when the viewer is unknown, and prefers T34's is_own when sent", () => {
    expect(adaptQueueItem(MOCK_QUEUE[2], null).isOwn).toBe(false);
    expect(adaptQueueItem({ ...MOCK_QUEUE[0], is_own: true }, MOCK_VIEWER_ID).isOwn).toBe(true);
    expect(adaptQueueItem({ ...MOCK_QUEUE[2], is_own: false }, MOCK_VIEWER_ID).isOwn).toBe(false);
  });

  it("names people, never by raw id, and describes decisions in words", () => {
    const c = adaptCase(MOCK_CASE_DECIDED);
    expect(c.decision?.by).toBe("Dr. B. Osei");
    expect(c.decision?.actionText).toBe("Approved");
    const anon = adaptCase({ ...MOCK_CASE_DECIDED, decision: { ...MOCK_CASE_DECIDED.decision!, reviewer_name: null } });
    expect(anon.decision?.by).toBe("Reviewer 7f3c2a");
  });

  it("describes system actions in words", () => {
    const c = adaptCase({ ...MOCK_CASE_DECIDED, audit_trail: [{ id: "x", actor_id: "system", actor_name: "System", action: "review_opened", entity_type: "review", entity_id: "r", created_at: "2026-11-23T09:00:00Z" }] });
    expect(c.audit[0]).toMatchObject({ who: "System", what: "Sent the case for review" });
  });

  it("orders the audit trail oldest first", () => {
    const c = adaptCase({ ...MOCK_CASE_DECIDED, audit_trail: [...MOCK_CASE_DECIDED.audit_trail!, { ...MOCK_CASE_DECIDED.audit_trail![0], id: "a0", created_at: "2026-11-23T09:00:00Z" }] });
    expect(c.audit.map((a) => a.id)).toEqual(["a0", "a2"]);
  });

  it.each([
    [30, "1 min"],
    [59 * 60, "59 min"],
    [3 * 3600, "3 h"],
    [47 * 3600, "47 h"],
    [72 * 3600, "3 d"],
  ])("%s s → %s", (s, out) => expect(waitingText(s)).toBe(out));
});
