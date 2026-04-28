import { notFound } from "next/navigation";
import { serverApiFetch } from "../../../lib/api-server";
import { JobDetailClient } from "./JobDetailClient";

async function fetchJob(jobId: string) {
  try {
    const res = await serverApiFetch(`/jobs/${jobId}`);
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchResult(jobId: string) {
  try {
    const res = await serverApiFetch(`/jobs/${jobId}/result`);
    if (res.status !== 200) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function JobDetailPage({
  params,
}: {
  params: { job_id: string };
}) {
  const job = await fetchJob(params.job_id);
  if (!job) notFound();

  const result = job.status === "SUCCESS" ? await fetchResult(params.job_id) : null;

  return <JobDetailClient jobId={params.job_id} initialJob={job} initialResult={result} />;
}
