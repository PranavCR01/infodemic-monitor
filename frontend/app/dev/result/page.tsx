import Link from "next/link";
import { ResultView } from "@/components/result/ResultView";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_RESULTS } from "@/lib/api/mocks/results";

export const metadata = { title: "Result preview (mock data) · WHO Infodemic Monitor" };

// Preview of the result screen on MOCK data (lib/api/mocks/results.ts), so the
// T26 / T30 / T31 fields can be reviewed before the backend returns them.
export default function ResultPreview({ searchParams }: { searchParams: { case?: string } }) {
  const key = searchParams.case && MOCK_RESULTS[searchParams.case] ? searchParams.case : "pending";
  return (
    <div className="mx-auto max-w-[1440px] px-4 py-6 md:px-8">
      <p role="note" className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small text-warn-fg">
        <strong>Mock data.</strong> Cases:
        {Object.keys(MOCK_RESULTS).map((k) => (
          <Link key={k} href={`/dev/result?case=${k}`} aria-current={k === key ? "page" : undefined} className={`underline ${k === key ? "font-bold" : ""}`}>
            {k}
          </Link>
        ))}
      </p>
      <ResultView result={adaptResult(MOCK_RESULTS[key])} />
    </div>
  );
}
