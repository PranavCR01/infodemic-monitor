import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/jobs/abc",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/supabase", () => ({
  getBrowserClient: () => ({
    auth: { onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }), signOut: vi.fn() },
  }),
}));

import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("shows the main nav, marks the current page and names the user", () => {
    render(
      <AppShell email="a.mensah@who-research.org" role="analyst">
        <p>content</p>
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Videos" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Submit" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("img", { name: "Signed in as a.mensah@who-research.org" })).toHaveTextContent("AM");
    expect(screen.getByRole("main")).toHaveTextContent("content");
    expect(screen.getByText("Skip to content")).toHaveAttribute("href", "#main");
  });

  it("doesn't show the session-expired dialog on load", () => {
    render(<AppShell email="x@y.org" role="analyst">ok</AppShell>);
    expect(screen.queryByText("Please sign in again")).not.toBeInTheDocument();
  });
});
