import { Suspense } from "react";
import { JobsClient } from "./JobsClient";

export const metadata = { title: "Your videos · WHO Infodemic Monitor" };

export default function JobsPage() {
  // useSearchParams (filters in the URL) needs a Suspense boundary.
  return (
    <Suspense fallback={<p className="text-small text-ink-2">Loading your videos…</p>}>
      <JobsClient />
    </Suspense>
  );
}
