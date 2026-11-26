import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Source } from "@/lib/api/result-adapter";
import { SourceList } from "./SourceList";

const src = (i: number): Source => ({
  id: `s${i}`, title: `Paper ${i}`, relation: "CONSIDERED", studyType: "rct", level: "RCT", kind: "pubmed",
  year: 2020, publisher: null, snippet: "", url: null, pmid: null,
});

describe("SourceList (T59)", () => {
  it("shows the first 3 in the order given, the rest behind 'Show N more sources'", () => {
    render(<SourceList sources={[1, 2, 3, 4, 5].map(src)} />);
    expect(screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Paper 1", "Paper 2", "Paper 3"]);
    const more = screen.getByRole("button", { name: "Show 2 more sources" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    expect(screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Paper 1", "Paper 2", "Paper 3", "Paper 4", "Paper 5"]);
    expect(screen.getByRole("button", { name: "Show fewer sources" })).toHaveAttribute("aria-expanded", "true");
  });

  it("moves keyboard focus to the first newly shown source", () => {
    render(<SourceList sources={[1, 2, 3, 4].map(src)} />);
    fireEvent.click(screen.getByRole("button", { name: "Show 1 more source" }));
    expect(document.activeElement).toHaveTextContent("Paper 4");
  });

  it("has no button when there are 3 or fewer, and nothing at all for none", () => {
    const { rerender, container } = render(<SourceList sources={[1, 2, 3].map(src)} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<SourceList sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
