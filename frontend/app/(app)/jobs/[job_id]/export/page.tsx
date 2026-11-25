import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { ExportReport } from "@/components/export/ExportReport";
import { PrintButton } from "@/components/export/PrintButton";
import { buttonClass, EmptyState } from "@/components/ui";
import { serverApiFetch } from "@/lib/api-server";
import { adaptResult } from "@/lib/api/result-adapter";

export const metadata = { title: "Report · WHO Infodemic Monitor" };

// HANDOFF §6.10: print view of a finished result, built from GET /jobs/{id}/result.
export default async function ExportPage({ params }: { params: { job_id: string } }) {
  let res: Response;
  try {
    res = await serverApiFetch(`/jobs/${encodeURIComponent(params.job_id)}/result`);
  } catch {
    res = new Response(null, { status: 503 });
  }
  if (res.status === 404) notFound();
  if (res.status !== 200) {
    return (
      <EmptyState
        icon="file"
        title="The report isn't ready"
        action={<Link href={`/jobs/${params.job_id}`} className={buttonClass("secondary", "sm")}>Back to the video</Link>}
      >
        A report can be made once the analysis has finished.
      </EmptyState>
    );
  }
  const r = adaptResult(await res.json());
  const h = headers();
  const recordUrl = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("host") ?? ""}/jobs/${params.job_id}`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href={`/jobs/${params.job_id}`} className="text-small text-primary underline">Back to the video</Link>
        <PrintButton />
      </div>
      <ExportReport r={r} recordUrl={recordUrl} />
    </div>
  );
}
