import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { adaptQueueItem } from "@/lib/api/review-adapter";
import { MOCK_QUEUE, MOCK_VIEWER_ID } from "@/lib/api/mocks/reviews";
import { ReviewQueue } from "./ReviewQueue";

const items = MOCK_QUEUE.map((i) => adaptQueueItem(i, MOCK_VIEWER_ID));
const view = (list = items) =>
  render(<ReviewQueue items={list} view="open" onViewChange={vi.fn()} hrefFor={(i) => `/review/${i.reviewId}`} />);

describe("ReviewQueue", () => {
  it("lists cases by priority then age, with plain-language reasons", () => {
    view();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual([
      "hot-water-flu.mp4",
      "sea-moss-thyroid.mp4",
      "lemon-detox.mp4",
      "ginger-tea-colds.mp4",
    ]);
    expect(screen.getByRole("table")).not.toHaveTextContent(/weak_evidence|judge:|_/);
  });

  it("gives no Review button on the reviewer's own submission", () => {
    view();
    const own = screen.getByText("lemon-detox.mp4").closest("tr")!;
    expect(within(own).queryByRole("link")).not.toBeInTheDocument();
    expect(within(own).getByText("Your submission. Another reviewer decides.")).toBeInTheDocument();
    expect(within(own).getByText("You")).toBeInTheDocument();
  });

  it("links each case to its workspace, with the file name for screen readers", () => {
    view();
    expect(screen.getByRole("link", { name: "Review hot-water-flu.mp4" })).toHaveAttribute("href", "/review/rev-1");
  });

  it("filters by reason", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: /no evidence supports it 1/ }));
    expect(screen.getAllByRole("row")).toHaveLength(2);
  });

  it("says when there's nothing to review", () => {
    view([]);
    expect(screen.getByText("Nothing to review")).toBeInTheDocument();
  });
});
