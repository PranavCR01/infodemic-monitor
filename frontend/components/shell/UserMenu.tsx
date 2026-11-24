"use client";

import { useRouter } from "next/navigation";
import { markIntentionalSignOut } from "./SessionWatcher";
import { getBrowserClient } from "@/lib/supabase";

export function UserMenu({ email, initials, roleLabel }: { email: string; initials: string; roleLabel: string }) {
  const router = useRouter();
  async function signOut() {
    markIntentionalSignOut();
    await getBrowserClient().auth.signOut();
    router.replace("/sign-in");
    router.refresh();
  }
  return (
    <div className="flex items-center gap-3">
      <span className="hidden text-right text-cap text-ink-3 md:block">
        <span className="block text-small text-ink-2">{email}</span>
        {roleLabel}
      </span>
      <span
        role="img"
        aria-label={`Signed in as ${email}`}
        className="grid h-8 w-8 place-items-center rounded-full bg-surface-sunken text-cap font-semibold text-ink"
      >
        {initials}
      </span>
      <button type="button" onClick={signOut} className="min-h-10 rounded-md px-2 text-small text-ink-2 hover:bg-surface-sunken hover:text-ink">
        Sign out
      </button>
    </div>
  );
}
