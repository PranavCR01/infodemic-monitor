import { ExportReport } from "@/components/export/ExportReport";
import { PrintButton } from "@/components/export/PrintButton";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_RESULTS } from "@/lib/api/mocks/results";

export const metadata = { title: "Report preview (mock data) · WHO Infodemic Monitor" };

export default function ExportPreview({ searchParams }: { searchParams: { case?: string } }) {
  const raw = MOCK_RESULTS[searchParams.case ?? "pending"] ?? MOCK_RESULTS.pending;
  return (
    <div className="mx-auto max-w-[900px] px-4 py-6">
      <p role="note" className="mb-4 flex items-center justify-between rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small text-warn-fg print:hidden">
        <strong>Mock data.</strong> <PrintButton />
      </p>
      <ExportReport r={adaptResult(raw)} recordUrl="https://monitor.example/jobs/mock" />
    </div>
  );
}
