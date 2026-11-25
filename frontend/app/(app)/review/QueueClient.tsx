"use client";

import { useCallback, useEffect, useState } from "react";
import { ReviewQueue } from "@/components/review/ReviewQueue";
import { ErrorBanner } from "@/components/ui";
import { fetchQueue } from "@/lib/api/reviews";
import type { QueueItem } from "@/lib/api/review-adapter";
import { useViewerId } from "@/lib/hooks/useViewerId";

export function QueueClient() {
  const [view, setView] = useState<"open" | "decided">("open");
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const viewerId = useViewerId();

  const load = useCallback(async () => {
    if (viewerId === undefined) return false;
    const r = await fetchQueue(view, viewerId);
    if (r.ok) {
      setItems(r.data.items);
      setError(null);
      setUpdatedAt(new Date());
    } else setError(r.message);
  }, [view, viewerId]);

  // HANDOFF §6.7: refresh every 30 s while the tab is visible.
  useEffect(() => {
    void load();
    const t = setInterval(() => {
      if (!document.hidden) void load();
    }, 30_000);
    return () => clearInterval(t);
  }, [load]);

  if (error && !items) return <ErrorBanner title="The review queue couldn't be loaded.">{error}</ErrorBanner>;
  if (!items) return <p className="text-small text-ink-2" aria-busy="true">Loading the queue…</p>;
  return <ReviewQueue items={items} view={view} onViewChange={setView} hrefFor={(i) => `/review/${i.reviewId}`} updatedAt={updatedAt} />;
}
