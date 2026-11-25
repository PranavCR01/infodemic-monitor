import type { JobState } from "@/lib/vocabulary";

export type JobFilters = { q: string; state: JobState | ""; label: string; needsReview: boolean; mine: boolean; page: number };
export const EMPTY_FILTERS: JobFilters = { q: "", state: "", label: "", needsReview: false, mine: false, page: 1 };
export const PAGE_SIZE = 20;
