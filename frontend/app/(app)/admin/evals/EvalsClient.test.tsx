import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }) }));
const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { MOCK_EVALS } from "@/lib/api/mocks/evals";
import { EvalsClient } from "./EvalsClient";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const FORBIDDEN = { detail: { code: "FORBIDDEN", message: "admin role required" } };

beforeEach(() => {
  apiFetch.mockReset();
  replace.mockReset();
});

describe("/admin/evals (T63)", () => {
  it("shows a loading state, then the list for an admin", async () => {
    apiFetch.mockResolvedValueOnce(json(200, MOCK_EVALS));
    render(<EvalsClient />);
    expect(screen.getByText("Loading evaluations…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Evaluations", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(6);
  });

  // The API answers 403 for analysts and reviewers (role checked server-side); the page
  // shows the not-authorised state, never an empty or partial list.
  it.each(["analyst", "reviewer"])("shows the not-authorised state to a %s (API 403)", async () => {
    apiFetch.mockResolvedValueOnce(json(403, FORBIDDEN));
    render(<EvalsClient />);
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
    expect(screen.getByText(/for administrators/)).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evaluations" })).not.toBeInTheDocument();
  });

  it("sends a signed-out user (API 401) to sign in, coming back here", async () => {
    apiFetch.mockResolvedValueOnce(json(401, { detail: "Not authenticated" }));
    render(<EvalsClient />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fadmin%2Fevals"));
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("shows an error with a retry when the service fails", async () => {
    apiFetch.mockResolvedValueOnce(json(500, {}));
    render(<EvalsClient />);
    expect(await screen.findByText("The evaluations couldn't be loaded.")).toBeInTheDocument();
    apiFetch.mockResolvedValueOnce(json(200, MOCK_EVALS));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Evaluations", level: 1 })).toBeInTheDocument();
  });

  it("shows the empty state when the registry is empty", async () => {
    apiFetch.mockResolvedValueOnce(json(200, { total: 0, step_order: [], groups: [], items: [] }));
    render(<EvalsClient />);
    expect(await screen.findByText("No evaluations recorded yet")).toBeInTheDocument();
  });
});
