import Link from "next/link";
import { buttonClass, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        icon="file"
        title="We can't find that page"
        action={
          <Link href="/jobs" className={buttonClass("secondary", "sm")}>
            Go to your videos
          </Link>
        }
      >
        The link may be wrong, or the page was moved.
      </EmptyState>
    </main>
  );
}
