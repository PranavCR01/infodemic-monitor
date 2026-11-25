import Link from "next/link";
import { buttonClass, EmptyState } from "@/components/ui";
import { isRole, ROLE_DISPLAY } from "@/lib/auth/roles";

export const metadata = { title: "No access · WHO Infodemic Monitor" };

// Rendered by the middleware (rewrite, HTTP 403) at the URL the user asked for.
export default function PermissionDenied({ searchParams }: { searchParams: { need?: string } }) {
  const need = isRole(searchParams.need) ? searchParams.need : null;
  const hint =
    need === "reviewer"
      ? "This page is for reviewers. Ask your project lead if you need reviewer access."
      : need === "admin"
        ? "This page is for administrators. Ask your project lead if you need access."
        : "Ask your project lead if you need access.";
  return (
    <div className="mx-auto max-w-xl py-12">
      <EmptyState
        icon="lock"
        title="You don't have access to this page"
        action={
          <Link href="/jobs" className={buttonClass("secondary", "sm")}>
            Go to your videos
          </Link>
        }
      >
        {hint}
        {need && <span className="sr-only"> Needed role: {ROLE_DISPLAY[need]}.</span>}
      </EmptyState>
    </div>
  );
}
