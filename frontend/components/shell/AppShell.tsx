import type { ReactNode } from "react";
import { ROLE_DISPLAY, type Role } from "@/lib/auth/roles";
import { Brand } from "./Brand";
import { initials, navFor } from "./nav";
import { NavLinks } from "./NavLinks";
import { SessionWatcher } from "./SessionWatcher";
import { UserMenu } from "./UserMenu";

type Props = { email: string | null; role: Role | null; children: ReactNode };

/** Top bar (Main.dc.html .topbar) + page column. Used by every signed-in page. */
export function AppShell({ email, role, children }: Props) {
  const items = navFor(role).map(({ href, label, icon }) => ({ href, label, icon }));
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="flex min-h-14 flex-wrap items-center gap-6 border-b border-line bg-surface px-4 print:hidden md:px-8">
        <Brand href="/jobs" />
        <NavLinks items={items} />
        {email && <UserMenu email={email} initials={initials(email)} roleLabel={role ? ROLE_DISPLAY[role] : ""} />}
      </header>
      <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 print:p-0 md:px-8">
        {children}
      </main>
      <SessionWatcher />
    </div>
  );
}
