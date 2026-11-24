import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_DEBUNKED_VERIFIED, MOCK_LEGACY, MOCK_MISINFO_PENDING, MOCK_NO_CLAIMS, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { ResultView } from "./ResultView";

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as never;
});

const INTERNAL = /\b(NO_MISINFO|DEBUNKING|CANNOT_RECOGNIZE|INSUFFICIENT_EVIDENCE|NOT_VERIFIABLE|REVIEW_REQUIRED|UNSUPPORTED|ENDORSED_CONTRADICTED)\b|\bclaim c\d\b|weak_evidence|judge:/;

describe("ResultView", () => {
  it.each([
    ["pending", MOCK_MISINFO_PENDING],
    ["debunked", MOCK_DEBUNKED_VERIFIED],
    ["unproven", MOCK_UNPROVEN],
    ["no claims", MOCK_NO_CLAIMS],
    ["legacy", MOCK_LEGACY],
  ])("shows no internal names (%s)", (_n, raw) => {
    const { container } = render(<ResultView result={adaptResult(raw)} />);
    expect(container.textContent).not.toMatch(INTERNAL);
  });

  it("marks a pending result as provisional and lists reasons by claim number", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Treat this label as provisional");
    expect(within(banner).getByText(/^Claim 3:/)).toBeInTheDocument();
    expect(screen.getByText("System assessment")).toBeInTheDocument();
    expect(screen.getByText("Pending review")).toBeInTheDocument();
  });

  it("never shows a confidence number", () => {
    const { container } = render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    expect(container.textContent).toMatch(/Not yet calibrated/);
    expect(container.textContent).not.toMatch(/0\.82|82 ?%/);
  });

  it("shows who confirmed a verified DEBUNKED result, with no review banner", () => {
    render(<ResultView result={adaptResult(MOCK_DEBUNKED_VERIFIED)} />);
    expect(screen.getAllByText("DEBUNKED").length).toBeGreaterThan(0);
    expect(screen.getByText(/Verified by a reviewer/)).toBeInTheDocument();
    expect(screen.queryByText(/provisional/)).not.toBeInTheDocument();
    expect(screen.getByText("The speaker refutes a claim the evidence contradicts. This corrects misinformation.")).toBeInTheDocument();
  });

  it("shows MISINFO (unproven) and never calls the claim false", () => {
    const { container } = render(<ResultView result={adaptResult(MOCK_UNPROVEN)} />);
    expect(screen.getAllByText("MISINFO (unproven)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No supporting evidence").length).toBeGreaterThan(0);
    expect(container.textContent?.toLowerCase()).not.toMatch(/\bis false\b|proven false(?! ;)/);
  });

  it("gives CANNOT RECOGNIZE its reason line", () => {
    render(<ResultView result={adaptResult(MOCK_NO_CLAIMS)} />);
    expect(screen.getByText(/No checkable health claims were found in the video\./, { selector: "p.text-small" })).toBeInTheDocument();
  });

  it("doesn't repeat the label description with a rule line for other labels", () => {
    const { container } = render(<ResultView result={adaptResult(MOCK_UNPROVEN)} />);
    expect(container.textContent).not.toMatch(/The speaker presents an untested remedy as working, and no evidence supports it\./);
  });

  it("explains a result without claim-level data", () => {
    render(<ResultView result={adaptResult(MOCK_LEGACY)} />);
    expect(screen.getByText(/without claim-by-claim checking/)).toBeInTheDocument();
  });

  it("selects a claim from the timeline, and the previous/next buttons move between claims", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    const seg2 = screen.getByRole("button", { name: /^Claim 2, 0:08 to 0:13, contradicted by evidence/ });
    expect(seg2).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(seg2);
    expect(seg2).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: /Next claim/ }));
    expect(screen.getByRole("button", { name: /^Claim 3, / })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Next claim/ })).toBeDisabled();
  });

  it("starts on the claim that decided the label", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    expect(screen.getByRole("button", { name: /^Claim 1, / })).toHaveAttribute("aria-pressed", "true");
  });
});
