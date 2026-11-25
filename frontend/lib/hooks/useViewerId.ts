"use client";

import { useEffect, useState } from "react";
import { getBrowserClient } from "@/lib/supabase";

/**
 * The signed-in user's id, read from the local session (no network call).
 * `undefined` while it is being read, `null` if there is no session. Callers wait for
 * `!== undefined` before loading, so a user's own rows are never shown as someone else's.
 */
export function useViewerId(): string | null | undefined {
  const [id, setId] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    getBrowserClient()
      .auth.getSession()
      .then(({ data }) => {
        if (live) setId(data.session?.user.id ?? null);
      })
      .catch(() => {
        if (live) setId(null);
      });
    return () => {
      live = false;
    };
  }, []);
  return id;
}
