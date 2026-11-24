import Link from "next/link";
import { JobProgress } from "@/components/jobs/JobProgress";
import { JobsList } from "@/components/jobs/JobsList";
import { adaptJobList, adaptProgress } from "@/lib/api/job-adapter";
import { MOCK_DONE, MOCK_FAILED, MOCK_JOB_PAGE, MOCK_QUEUED, MOCK_RETRYING, MOCK_RUNNING } from "@/lib/api/mocks/jobs";
import { EMPTY_FILTERS } from "@/lib/job-filters";

export const metadata = { title: "Jobs preview (mock data) · WHO Infodemic Monitor" };

const CASES = { running: MOCK_RUNNING, retrying: MOCK_RETRYING, failed: MOCK_FAILED, queued: MOCK_QUEUED, done: MOCK_DONE };

// MOCK data in T28's shapes. Server-rendered, so no buttons act.
export default function JobsPreview({ searchParams }: { searchParams: { case?: string } }) {
  const raw = CASES[searchParams.case as keyof typeof CASES];
  const { rows, total } = adaptJobList(MOCK_JOB_PAGE);
  return (
    <div className="mx-auto max-w-[1440px] px-4 py-6 md:px-8">
      <p role="note" className="mb-4 flex flex-wrap gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small text-warn-fg">
        <strong>Mock data.</strong>
        {["list", ...Object.keys(CASES)].map((k) => (
          <Link key={k} href={k === "list" ? "/dev/jobs" : `/dev/jobs?case=${k}`} className="underline">{k}</Link>
        ))}
      </p>
      {raw ? (
        <JobProgress filename="hot-water-flu.mp4" jobId={raw.job_id} errorCode={raw.state === "FAILED" ? "TRANSCRIPTION_ERROR" : null} progress={adaptProgress(raw)} lost={false} onCheckNow={undefined as never} />
      ) : (
        <JobsList rows={rows} total={total} filters={EMPTY_FILTERS} onFilters={undefined as never} error={null} />
      )}
    </div>
  );
}
