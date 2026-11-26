import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_MISINFO_PENDING } from "@/lib/api/mocks/results";
import type { RawResult } from "@/lib/api/result-types";
import { ResultView } from "./ResultView";
import { sortSources } from "./SourceCard";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as never;
});
beforeEach(() => window.history.replaceState(null, "", "/jobs/mock-job-1"));

const open = (n: number) => {
  const card = screen.getByRole("article", { name: `Claim ${n}` });
  fireEvent.click(within(card).getByRole("button", { name: /details/i }));
  return screen.getByRole("dialog");
};

describe("ClaimDrawer", () => {
  it("opens from a claim card as a dialog titled with the claim, and puts the claim in the URL", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    expect(within(dialog).getByRole("heading", { level: 2, name: /Drinking hot water/ })).toBeInTheDocument();
    expect(within(dialog).getByText("Claim 1 of 3")).toBeInTheDocument();
    expect(window.location.search).toBe("?claim=c1");
  });

  it("opens straight from a shared link", () => {
    window.history.replaceState(null, "", "/jobs/mock-job-1?claim=c2");
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    expect(within(screen.getByRole("dialog")).getByText("Claim 2 of 3")).toBeInTheDocument();
  });

  it("ignores a link to a claim that doesn't exist", () => {
    window.history.replaceState(null, "", "/jobs/mock-job-1?claim=zz");
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape and clears the URL", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  it("returns focus to the claim's details button when it closes", async () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "Next claim" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    const target = within(screen.getByRole("article", { name: "Claim 2" })).getByRole("button", { name: /details/i });
    await waitFor(() => expect(document.activeElement).toBe(target));
  });

  it("moves between claims with previous and next", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    expect(within(dialog).getByRole("button", { name: "Previous claim" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Next claim" }));
    expect(within(screen.getByRole("dialog")).getByText("Claim 2 of 3")).toBeInTheDocument();
    expect(window.location.search).toBe("?claim=c2");
  });

  it("opens on the sources that match the verdict and can switch", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    const contradicts = within(dialog).getByRole("button", { name: /Contradicts 2/ });
    expect(contradicts).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getAllByRole("article")).toHaveLength(2);
    fireEvent.click(within(dialog).getByRole("button", { name: /Supports 0/ }));
    expect(within(dialog).getByText("No source supports this claim.")).toBeInTheDocument();
  });

  it("says plainly when no source tests a claim", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(3);
    expect(within(dialog).getByText("No source was found that tests this claim.")).toBeInTheDocument();
    expect(within(dialog).getByText(/Claim is broader than any study/)).toBeInTheDocument();
  });

  it("shows quotes and the fixed meaning line, but not the critic's pipeline notes (T52)", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(1);
    expect(within(dialog).getByText("HOT WATER = NO MORE FLU")).toBeInTheDocument();
    expect(within(dialog).getByText("The speaker promotes a claim that the evidence contradicts.")).toBeInTheDocument();
    expect(within(dialog).queryByText(/Critic's notes/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/The trial population was adults with common cold/)).not.toBeInTheDocument();
  });

  it("links PubMed and official sources, and never links internal library documents", () => {
    const raw: RawResult = {
      ...MOCK_MISINFO_PENDING,
      claims: [
        {
          ...MOCK_MISINFO_PENDING.claims![0],
          evidence: [
            ...MOCK_MISINFO_PENDING.claims![0].evidence!,
            { evidence_id: "lib", title: "Lab handbook", relation: "CONTRADICTS", source_kind: "library", study_type: "guideline", url: "https://internal.example/doc" },
          ],
        },
      ],
    };
    render(<ResultView result={adaptResult(raw)} />);
    const dialog = open(1);
    expect(within(dialog).getByRole("link", { name: /View on PubMed/ })).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/00000001/");
    expect(within(dialog).getByRole("link", { name: /Open on who\.int/ })).toBeInTheDocument();
    const lib = within(dialog).getByText("Lab handbook").closest("article")!;
    expect(within(lib).queryByRole("link")).not.toBeInTheDocument();
    expect(within(lib).getByText(/Internal only/)).toBeInTheDocument();
  });

  it("copies the link to the claim", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(2);
    fireEvent.click(within(dialog).getByRole("button", { name: /Copy link to claim/ }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("?claim=c2"));
    expect(await within(dialog).findByText("Link copied.")).toBeInTheDocument();
  });
});

describe("ClaimDrawer: how we searched (T31, T52)", () => {
  it("says in one plain finding how the search went, with no raw queries or technical details", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const dialog = open(3);
    const section = within(dialog).getByRole("region", { name: "How we searched" });
    expect(section).toHaveTextContent(
      "No relevant study was found after 2 searches. 3 papers were retrieved and none was relevant enough to check the claim against, so this claim could not be checked and was sent to a reviewer.",
    );
    expect(section).toHaveTextContent(/document library was searched too/);
    expect(within(section).getByText(/titles of the papers that weren't relevant enough to check weren't kept/)).toBeInTheDocument();
    expect(within(dialog).queryByText("vitamin C megadose viral infection prevention")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Technical details")).not.toBeInTheDocument();
  });

  it("lists papers retrieved but not used, collapsed, with PubMed links", () => {
    const raw: RawResult = {
      ...MOCK_MISINFO_PENDING,
      claims: [
        {
          ...MOCK_MISINFO_PENDING.claims![0],
          evidence: [
            ...MOCK_MISINFO_PENDING.claims![0].evidence!,
            { evidence_id: "off", title: "Vitamin D and bone density in older women", relation: "CONSIDERED", source_kind: "pubmed", pmid: "12345678", study_type: "cohort", year: 2017 },
          ],
        },
      ],
    };
    render(<ResultView result={adaptResult(raw)} />);
    const dialog = open(1);
    const details = within(dialog).getByText(/Papers retrieved but not used/).closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText(/\(1\)/)).toBeInTheDocument();
    expect(within(details).getByRole("link", { name: /Vitamin D and bone density/ })).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/12345678/");
  });
});

describe("sortSources", () => {
  it("orders by strength of study type, not by count", () => {
    const s = adaptResult(MOCK_MISINFO_PENDING).claims[0].sources;
    const mixed = [{ ...s[1], id: "g" }, { ...s[0], id: "rct" }, { ...s[0], id: "sr", level: "SYSTEMATIC_REVIEW" as const }, { ...s[0], id: "none", level: null }];
    expect(sortSources(mixed).map((x) => x.id)).toEqual(["sr", "rct", "g", "none"]);
  });
});
