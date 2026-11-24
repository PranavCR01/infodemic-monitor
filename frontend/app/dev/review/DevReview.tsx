"use client";

import { useState } from "react";
import { ReviewQueue } from "@/components/review/ReviewQueue";
import { ReviewWorkspace } from "@/components/review/ReviewWorkspace";
import { adaptResult } from "@/lib/api/result-adapter";
import { adaptCase, adaptQueueItem } from "@/lib/api/review-adapter";
import { MOCK_MISINFO_PENDING, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { MOCK_CASE_DECIDED, MOCK_CASE_HIGH, MOCK_CASE_OWN, MOCK_QUEUE } from "@/lib/api/mocks/reviews";

const CASES = {
  high: { review: MOCK_CASE_HIGH, result: MOCK_MISINFO_PENDING },
  normal: { review: { ...MOCK_CASE_HIGH, severity: "MEDIUM" }, result: MOCK_MISINFO_PENDING },
  decided: { review: MOCK_CASE_DECIDED, result: MOCK_UNPROVEN },
  own: { review: MOCK_CASE_OWN, result: MOCK_MISINFO_PENDING },
};

/** MOCK data: decisions are not sent anywhere. */
export function DevReview({ which }: { which: string | undefined }) {
  const [view, setView] = useState<"open" | "decided">("open");
  const c = CASES[which as keyof typeof CASES];
  if (!c) {
    const items = MOCK_QUEUE.map(adaptQueueItem).filter((i) => (view === "open" ? i.open : !i.open));
    return <ReviewQueue items={items} view={view} onViewChange={setView} hrefFor={(i) => `/dev/review?case=${i.severity === "HIGH" ? "high" : "normal"}`} updatedAt={null} />;
  }
  return (
    <ReviewWorkspace
      review={adaptCase(c.review)}
      result={adaptResult(c.result)}
      onDecide={async () => ({ ok: true })}
      onOverrideSeverity={async () => ({ ok: true })}
    />
  );
}
