import Link from "next/link";
import { DevReview } from "./DevReview";

export const metadata = { title: "Review preview (mock data) · WHO Infodemic Monitor" };

export default function ReviewPreview({ searchParams }: { searchParams: { case?: string } }) {
  return (
    <div className="mx-auto max-w-[1440px] px-4 py-6 md:px-8">
      <p role="note" className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small text-warn-fg">
        <strong>Mock data; nothing is saved.</strong>
        {["queue", "high", "normal", "decided", "own"].map((k) => (
          <Link key={k} href={k === "queue" ? "/dev/review" : `/dev/review?case=${k}`} className="underline">{k}</Link>
        ))}
      </p>
      <DevReview which={searchParams.case} />
    </div>
  );
}
