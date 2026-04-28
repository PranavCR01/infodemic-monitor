import Link from "next/link";
import { serverApiFetch } from "../../lib/api-server";
import { JobsView } from "./JobsView";
import { SignOutButton } from "../components/SignOutButton";

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
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-[#009edb] flex items-center justify-center">
              <span className="text-white font-bold text-xs">WHO</span>
            </div>
            <span className="font-semibold text-gray-900 text-sm">Infodemic Monitor</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/" className="text-gray-500 hover:text-gray-900 transition-colors">
              Upload
            </Link>
            <SignOutButton />
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <h1 className="text-xl font-semibold text-gray-900 mb-6">Job History</h1>
        <JobsView initialJobs={jobs} />
      </main>
    </div>
  );
}
