"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { JobsList } from "@/components/jobs/JobsList";
import { fetchJobs, filtersFromSearch, searchFromFilters } from "@/lib/api/jobs";
import type { JobRow } from "@/lib/api/job-adapter";
import { usePolling } from "@/lib/hooks/usePolling";
import type { JobFilters } from "@/lib/job-filters";
import { useViewerId } from "@/lib/hooks/useViewerId";

export function JobsClient() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const filters = useMemo(() => filtersFromSearch(new URLSearchParams(params?.toString() ?? "")), [params]);
  const [rows, setRows] = useState<JobRow[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const viewerId = useViewerId();

  const load = useCallback(async () => {
    if (viewerId === undefined) return false;
    const r = await fetchJobs(filters, viewerId);
    if (!r) {
      setError("We couldn't load your videos. We'll keep trying.");
      return false;
    }
    setRows(r.rows);
    setTotal(r.total);
    setError(null);
    return true;
  }, [filters, viewerId]);

  useEffect(() => {
    setRows(null);
    void load();
  }, [load]);

  // HANDOFF §6.3: every 10 s, only while a visible row is queued, running or retrying.
  const anyActive = rows?.some((r) => r.active) ?? false;
  usePolling(load, !anyActive, { fastMs: 10_000, slowMs: 10_000 });

  const setFilters = (f: JobFilters) => router.replace(`${path}${searchFromFilters(f)}`, { scroll: false });
  return <JobsList rows={rows} total={total} filters={filters} onFilters={setFilters} error={error} />;
}
