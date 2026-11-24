import { serverApiFetch } from "@/lib/api-server";
import { JobsView } from "./JobsView";

async function fetchJobs() {
  try {
    const res = await serverApiFetch("/jobs?limit=50");
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function JobsPage() {
  const jobs = await fetchJobs();

  return (
    <div className="flex flex-col">
      <div className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <h1 className="text-xl font-semibold text-gray-900 mb-6">Job History</h1>
        <JobsView initialJobs={jobs} />
      </div>
    </div>
  );
}
