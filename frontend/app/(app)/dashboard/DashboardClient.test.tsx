import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }) }));
const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { MOCK_STATS_30D, MOCK_STATS_7D_SMALL, MOCK_STATS_ALL } from "@/lib/api/mocks/stats";
import { DashboardClient } from "./DashboardClient";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const NOTE = "These figures describe videos uploaded to this tool, not how common misinformation is online.";
const section = (name: string) => screen.getByRole("region", { name });

beforeEach(() => {
  apiFetch.mockReset();
  replace.mockReset();
});

async function shown(body = MOCK_STATS_30D) {
  apiFetch.mockResolvedValueOnce(json(200, body));
  render(<DashboardClient />);
  await screen.findByRole("region", { name: "Videos analysed per week" });
}

describe("/dashboard (T62)", () => {
  it("loads the last 30 days by default", async () => {
    await shown();
    expect(apiFetch).toHaveBeenCalledWith("/v1/stats?window=30d");
    expect(screen.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("always shows the note: while loading, on an error and with figures", async () => {
    apiFetch.mockResolvedValueOnce(json(500, {}));
    render(<DashboardClient />);
    expect(screen.getByRole("note")).toHaveTextContent(NOTE);
    expect(await screen.findByText("The figures couldn't be loaded.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(NOTE);
    apiFetch.mockResolvedValueOnce(json(200, MOCK_STATS_30D));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("region", { name: "Videos analysed per week" });
    expect(screen.getByRole("note")).toHaveTextContent(NOTE);
  });

  it("shows suppressed cells as <5 and never plots them as a number", async () => {
    await shown();
    const weekly = section("Videos analysed per week");
    const rows = within(weekly).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(5);
    const hidden = rows.slice(0, 4);
    for (const r of hidden) {
      expect(within(r).getAllByRole("cell")[0]).toHaveTextContent("<5");
      expect(within(r).getAllByRole("cell")[0]).not.toHaveTextContent(/\b0\b/);
      expect(r.querySelector('[data-bar="suppressed"]')).not.toBeNull();
      expect(r.querySelector("[style]")).toBeNull(); // no bar with a width
    }
    // The published week sets the scale alone: 19 is the full bar.
    expect(rows[4].querySelector('[data-bar="19"]')).toHaveStyle({ width: "100%" });
    // Screen readers hear "fewer than 5", not a number.
    expect(within(hidden[0]).getByText("fewer than 5")).toBeInTheDocument();
  });

  it("shows a hidden summary figure as <5", async () => {
    await shown();
    const card = screen.getByText("Waiting for a reviewer").closest("li")!;
    expect(card.querySelector("[data-cell]")).toHaveAttribute("data-cell", "suppressed");
    expect(card).toHaveTextContent("<5");
  });

  it("says 'not enough decisions' when the share or median is null", async () => {
    await shown();
    const reviews = section("Reviews");
    const share = within(reviews).getByText("Share that changed the label").parentElement!;
    expect(share).toHaveTextContent("Not enough decisions");
    expect(share).not.toHaveTextContent("%");
    expect(within(reviews).getByText("Median time to a decision").parentElement!).toHaveTextContent("4.5 hours");
  });

  it("shows the share and median when there are enough decisions", async () => {
    await shown(MOCK_STATS_ALL);
    const reviews = section("Reviews");
    expect(within(reviews).getByText("Share that changed the label").parentElement!).toHaveTextContent("25%");
    expect(within(reviews).getByText("Median time to a decision").parentElement!).toHaveTextContent("6.2 hours");
    expect(within(reviews).queryByText("Not enough decisions")).not.toBeInTheDocument();
  });

  it("switches window and fetches again", async () => {
    await shown();
    apiFetch.mockResolvedValueOnce(json(200, MOCK_STATS_ALL));
    fireEvent.click(screen.getByRole("button", { name: "All time" }));
    expect(screen.getByRole("button", { name: "All time" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(apiFetch).toHaveBeenLastCalledWith("/v1/stats?window=all"));
    await screen.findByText(/Figures for all time/);
    expect(screen.getByText("Videos analysed").closest("li")).toHaveTextContent("120");
  });

  it("never shows a slower answer for an earlier window over the current one", async () => {
    let resolveFirst: (r: Response) => void = () => {};
    apiFetch.mockReturnValueOnce(new Promise<Response>((r) => (resolveFirst = r)));
    render(<DashboardClient />);
    apiFetch.mockResolvedValueOnce(json(200, MOCK_STATS_ALL));
    fireEvent.click(screen.getByRole("button", { name: "All time" }));
    await screen.findByText(/Figures for all time/);
    resolveFirst(json(200, MOCK_STATS_30D));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByText(/Figures for all time/)).toBeInTheDocument();
  });

  it("hides whole groups when the total is under 5", async () => {
    await shown(MOCK_STATS_7D_SMALL);
    expect(within(section("Videos analysed per week")).getByText(/Fewer than 5 videos were analysed/)).toBeInTheDocument();
    expect(within(section("Labels given by the system")).getByText(/so the labels are hidden/)).toBeInTheDocument();
    expect(within(section("Most common claim types")).getByText(/No claim type reached 5 videos/)).toBeInTheDocument();
    expect(screen.queryAllByRole("table")).toHaveLength(0);
  });

  it("hides the MISINFO split when MISINFO itself is under 5", async () => {
    const raw = { ...MOCK_STATS_30D, labels: { ...MOCK_STATS_30D.labels, MISINFO: "<5" as const } };
    await shown(raw);
    expect(within(section("Labels given by the system")).getByText(/Fewer than 5 videos were labelled MISINFO/)).toBeInTheDocument();
  });

  it("links to no video, job or uploader", async () => {
    await shown(MOCK_STATS_ALL);
    const main = document.body;
    const links = Array.from(main.querySelectorAll("a"));
    expect(links.filter((a) => /\/jobs\/|\/review\/|\/videos\//.test(a.getAttribute("href") ?? ""))).toHaveLength(0);
    expect(main).not.toHaveTextContent(/@|\.mp4|User [0-9a-f]{6}/);
  });

  it("gives every chart a table with row headers and text counts", async () => {
    await shown(MOCK_STATS_ALL);
    const labels = within(section("Labels given by the system")).getAllByRole("table")[0];
    expect(within(labels).getAllByRole("rowheader").map((h) => h.firstChild?.textContent)).toEqual(["MISINFO", "NO-MISINFO", "DEBUNKED", "CANNOT RECOGNIZE"]);
    expect(labels).toHaveTextContent("50");
  });

  it("sends a signed-out user (401) to sign in, coming back here", async () => {
    apiFetch.mockResolvedValueOnce(json(401, {}));
    render(<DashboardClient />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fdashboard"));
  });
});
