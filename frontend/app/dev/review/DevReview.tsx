"use client";

import { useState } from "react";
import type { RawCase } from "@/lib/api/review-types";
import { ReviewQueue } from "@/components/review/ReviewQueue";
import { ReviewWorkspace } from "@/components/review/ReviewWorkspace";
import { adaptResult } from "@/lib/api/result-adapter";
import { adaptCase, adaptQueueItem } from "@/lib/api/review-adapter";
import { MOCK_MISINFO_PENDING, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { MOCK_CASE_DECIDED, MOCK_CASE_HIGH, MOCK_CASE_NORMAL, MOCK_CASE_OWN, MOCK_QUEUE, MOCK_VIEWER_ID, mockRevealed } from "@/lib/api/mocks/reviews";

const CASES = {
  high: { review: MOCK_CASE_HIGH, result: MOCK_MISINFO_PENDING },
  normal: { review: MOCK_CASE_NORMAL, result: MOCK_MISINFO_PENDING },
  decided: { review: MOCK_CASE_DECIDED, result: MOCK_UNPROVEN },
  own: { review: MOCK_CASE_OWN, result: MOCK_MISINFO_PENDING },
};

/** MOCK data: decisions are not sent anywhere. */
export function DevReview({ which }: { which: string | undefined }) {
  const [view, setView] = useState<"open" | "decided">("open");
  const c = CASES[which as keyof typeof CASES];
  // Stands in for the server: POST /pre-reveal answers with the revealed case.
  const [revealed, setRevealed] = useState<RawCase | null>(null);
  if (!c) {
    const items = MOCK_QUEUE.map((i) => adaptQueueItem(i, MOCK_VIEWER_ID)).filter((i) => (view === "open" ? i.open : !i.open));
    return <ReviewQueue items={items} view={view} onViewChange={setView} hrefFor={(i) => `/dev/review?case=${i.reviewId === "rev-1" ? "high" : i.isOwn ? "own" : "normal"}`} updatedAt={null} />;
  }
  return (
    <ReviewWorkspace
      review={adaptCase(revealed ?? c.review, MOCK_VIEWER_ID)}
      result={adaptResult(c.result)}
      onDecide={async () => ({ ok: true })}
      onPreReveal={async (body) => {
        setRevealed(mockRevealed(body.claims));
        return { ok: true };
      }}
      onOverrideSeverity={async () => ({ ok: true })}
    />
  );
}
