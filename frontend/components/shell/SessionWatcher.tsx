"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { buttonClass } from "@/components/ui";
import { getBrowserClient } from "@/lib/supabase";

let intentional = false;
/** Called before our own sign-out, so it doesn't show the "session expired" dialog. */
export function markIntentionalSignOut() {
  intentional = true;
}

/**
 * States.dc.html "Session expired": a modal over the current page, so work on it
 * isn't thrown away by a redirect. Shown when Supabase reports the session ended
 * without the user signing out here (expiry, revoked, signed out in another tab).
 */
export function SessionWatcher() {
  const [expired, setExpired] = useState(false);
  const path = usePathname();
  useEffect(() => {
    const { data } = getBrowserClient().auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT" && !intentional) setExpired(true);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const signInHref = `/sign-in?next=${encodeURIComponent(path)}`;
  return (
    <Dialog.Root open={expired}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Content
          onEscapeKeyDown={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => e.preventDefault()}
          className="fixed left-1/2 top-1/3 z-50 flex w-[min(440px,calc(100vw-32px))] -translate-x-1/2 flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-3"
        >
          <Dialog.Title className="text-h3 text-ink">Please sign in again</Dialog.Title>
          <Dialog.Description className="text-small text-ink-2">
            For security, you were signed out. Anything you typed on this page is still here until you leave it.
          </Dialog.Description>
          <div className="flex gap-2">
            <a href={signInHref} className={buttonClass("primary", "sm")}>
              Sign in
            </a>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
