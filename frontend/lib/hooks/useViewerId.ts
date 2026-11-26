"use client";

import { useEffect, useState } from "react";
import { roleOf, type Role } from "@/lib/auth/roles";
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

/**
 * T55: the signed-in user's id and role, from the local session. `undefined` while it is
 * being read, `null` with no session. For showing controls only: the server checks again.
 */
export function useViewer(): { id: string; role: Role | null } | null | undefined {
  const [viewer, setViewer] = useState<{ id: string; role: Role | null } | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    getBrowserClient()
      .auth.getSession()
      .then(({ data }) => {
        const u = data.session?.user;
        if (live) setViewer(u ? { id: u.id, role: roleOf(u) } : null);
      })
      .catch(() => {
        if (live) setViewer(null);
      });
    return () => {
      live = false;
    };
  }, []);
  return viewer;
}

/** T55: the video's owner (the job's submitter) or an admin may re-analyse it. */
export function mayReanalyse(viewer: { id: string; role: Role | null } | null | undefined, submittedBy: string | null): boolean {
  if (!viewer) return false;
  return viewer.role === "admin" || (submittedBy !== null && submittedBy === viewer.id);
}
