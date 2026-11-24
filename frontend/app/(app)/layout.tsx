import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { roleOf } from "@/lib/auth/roles";
import { getServerClient } from "@/lib/supabase-server";

// Every signed-in page. The middleware has already checked sign-in and role.
export default async function AppLayout({ children }: { children: ReactNode }) {
  const {
    data: { user },
  } = await getServerClient().auth.getUser();
  return (
    <AppShell email={user?.email ?? null} role={roleOf(user)}>
      {children}
    </AppShell>
  );
}
