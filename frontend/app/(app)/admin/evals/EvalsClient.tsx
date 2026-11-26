"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EvalsList } from "@/components/admin/EvalsList";
import { Button, buttonClass, EmptyState, ErrorBanner } from "@/components/ui";
import { fetchEvals, type EvalsLoad } from "@/lib/api/evals";

/**
 * T63. The middleware already keeps non-admins out (lib/auth/roles.ts); the API checks
 * the role again, so a 403 here (e.g. a role removed since sign-in) shows the same
 * not-authorised state, and a 401 goes to sign-in.
 */
export function EvalsClient() {
  const router = useRouter();
  const [state, setState] = useState<EvalsLoad | null>(null);

  const load = useCallback(async () => {
    setState(null);
    setState(await fetchEvals());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state?.kind === "sign-in") router.replace(`/sign-in?next=${encodeURIComponent("/admin/evals")}`);
  }, [state, router]);

  if (state === null || state.kind === "sign-in") {
    return (
      <p className="text-small text-ink-2" aria-busy="true" role="status">
        {state === null ? "Loading evaluations…" : "Your session has ended. Taking you to sign in…"}
      </p>
    );
  }
  if (state.kind === "forbidden") return <NotAuthorised />;
  if (state.kind === "error") {
    return (
      <ErrorBanner
        title="The evaluations couldn't be loaded."
        action={
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Try again
          </Button>
        }
      >
        {state.message}
      </ErrorBanner>
    );
  }
  return <EvalsList runs={state.data.runs} />;
}

export function NotAuthorised() {
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
        This page is for administrators. Ask your project lead if you need access.
      </EmptyState>
    </div>
  );
}
