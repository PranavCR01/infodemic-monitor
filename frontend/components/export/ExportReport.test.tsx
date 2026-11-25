import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_DEBUNKED_VERIFIED, MOCK_LEGACY, MOCK_MISINFO_PENDING, MOCK_NO_CLAIMS, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { ExportReport } from "./ExportReport";

const show = (raw = MOCK_MISINFO_PENDING) => render(<ExportReport r={adaptResult(raw)} recordUrl="https://monitor.example/jobs/x" />);
const INTERNAL = /\b(NO_MISINFO|DEBUNKING|CANNOT_RECOGNIZE|INSUFFICIENT_EVIDENCE|REVIEW_REQUIRED)\b|\bclaim c\d\b|gpt-|claude-|model_used/;

describe("ExportReport", () => {
  it.each([MOCK_MISINFO_PENDING, MOCK_DEBUNKED_VERIFIED, MOCK_UNPROVEN, MOCK_NO_CLAIMS, MOCK_LEGACY])("prints no internal names or model IDs (%#)", (raw) => {
    const { container } = show(raw);
    expect(container.textContent).not.toMatch(INTERNAL);
  });

  it("never prints the label without its one-sentence rationale", () => {
    show();
    expect(screen.getByText("MISINFO")).toBeInTheDocument();
    expect(screen.getByText("Promotes a health claim the evidence contradicts.")).toBeInTheDocument();
    expect(screen.getByText(/A randomised trial and WHO guidance/)).toBeInTheDocument();
  });

  it("marks a pending result as provisional and as a system assessment", () => {
    show();
    expect(screen.getByText(/Pending review\. Treat the label as provisional\./)).toBeInTheDocument();
    expect(screen.getByText("System assessment")).toBeInTheDocument();
  });

  it("prints the analysis version and time so a report can be traced", () => {
    show();
    expect(screen.getByText("Analysis version")).toBeInTheDocument();
    expect(screen.getByText("graph_v1+3f9c2ab+p1a2b3c4d")).toBeInTheDocument();
    expect(screen.getByText("23 Nov 2026, 09:13 UTC")).toBeInTheDocument();
  });

  it("never prints T36's routing snapshot (model and prompt names)", () => {
    const { container } = show();
    expect(container).not.toHaveTextContent(/mock-model|claims_v3|verify_v2/);
  });

  it("leaves the version row out when the result has none", () => {
    show(MOCK_LEGACY);
    expect(screen.queryByText("Analysis version")).not.toBeInTheDocument();
  });

  it("marks an analyst-confirmed result", () => {
    show(MOCK_DEBUNKED_VERIFIED);
    expect(screen.getByText("Analyst-confirmed (verified)")).toBeInTheDocument();
  });

  it("prints no label for a rejected result", () => {
    const { container } = show({ ...MOCK_MISINFO_PENDING, review: { ...MOCK_MISINFO_PENDING.review!, status: "REJECTED" } });
    expect(screen.getByText(/No label\. A reviewer rejected this analysis\./)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\bMISINFO\b/);
  });

  it("prints verdicts and stances as words, with the deciding claim starred", () => {
    show();
    expect(screen.getByText(/★ 1\. Drinking hot water/)).toBeInTheDocument();
    expect(screen.getAllByText("ENDORSES").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Contradicted by evidence").length).toBeGreaterThan(0);
    expect(screen.getByText(/PMID 00000001/)).toBeInTheDocument();
  });

  it("says MISINFO (unproven) and that no evidence supports the claim", () => {
    show(MOCK_UNPROVEN);
    expect(screen.getByText("MISINFO (unproven)")).toBeInTheDocument();
    expect(screen.getByText("No supporting evidence")).toBeInTheDocument();
  });

  it("gives CANNOT RECOGNIZE its reason", () => {
    show(MOCK_NO_CLAIMS);
    expect(screen.getByText("No checkable health claims were found in the video.")).toBeInTheDocument();
  });
});
