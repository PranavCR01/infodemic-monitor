import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobStateTag, LabelBadge, ReviewReasonChip, StanceChip, VerdictChip } from ".";

describe("LabelBadge", () => {
  it("renders the display name with a decorative icon", () => {
    const { container } = render(<LabelBadge label="DEBUNKING" />);
    expect(screen.getByText("DEBUNKED")).toBeInTheDocument();
    const icon = container.querySelector("[data-icon]");
    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(icon).toHaveAttribute("data-icon", "shield");
  });

  it("never renders the internal name", () => {
    const { container } = render(<LabelBadge label="NO_MISINFO" />);
    expect(container.textContent).not.toContain("NO_MISINFO");
    expect(container.textContent).toContain("NO-MISINFO");
  });

  it("dashes CANNOT RECOGNIZE", () => {
    render(<LabelBadge label="CANNOT_RECOGNIZE" />);
    expect(screen.getByText("CANNOT RECOGNIZE").className).toContain("border-dashed");
  });

  it("shows MISINFO (unproven)", () => {
    render(<LabelBadge label="MISINFO" basis="unproven" showDescription />);
    expect(screen.getByText("MISINFO (unproven)")).toBeInTheDocument();
    expect(screen.getByText(/No evidence supports it/)).toBeInTheDocument();
  });
});

describe("VerdictChip", () => {
  it("draws insufficient evidence unfilled and dashed, in grey", () => {
    render(<VerdictChip verdict="INSUFFICIENT_EVIDENCE" />);
    const el = screen.getByText("Insufficient evidence");
    expect(el.className).toContain("border-dashed");
    expect(el.className).toContain("!bg-transparent");
    expect(el.className).toContain("text-abstain-fg");
  });

  it("draws contradicted filled and solid", () => {
    render(<VerdictChip verdict="CONTRADICTED" />);
    const el = screen.getByText("Contradicted by evidence");
    expect(el.className).not.toContain("border-dashed");
    expect(el.className).toContain("bg-misinfo-bg");
  });

  it("draws unsupported unfilled, dashed and rust", () => {
    render(<VerdictChip verdict="UNSUPPORTED" />);
    const el = screen.getByText("No supporting evidence");
    expect(el.className).toContain("border-dashed");
    expect(el.className).toContain("text-misinfo-fg");
    expect(el.className).not.toContain("bg-misinfo-bg");
  });
});

describe("StanceChip", () => {
  it("has no colour tone", () => {
    render(<StanceChip stance="REFUTES" />);
    const el = screen.getByText("REFUTES");
    expect(el.className).not.toMatch(/misinfo|debunked|abstain|mixed/);
  });
});

describe("JobStateTag", () => {
  it("maps legacy states", () => {
    render(<JobStateTag status="REVIEW_REQUIRED" />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("hides unknown raw states", () => {
    const { container } = render(<JobStateTag status="WEIRD_STATE" />);
    expect(container.textContent).toBe("Unknown state");
  });
});

describe("ReviewReasonChip", () => {
  it("prefers the API's text", () => {
    render(<ReviewReasonChip code="weak_evidence:c1" text="Server sentence." />);
    expect(screen.getByText("Server sentence.")).toBeInTheDocument();
  });

  it("falls back to the vocabulary, never the code", () => {
    const { container } = render(<ReviewReasonChip code="weak_evidence:c1" />);
    expect(container.textContent).not.toContain("weak_evidence");
    expect(container.textContent).toContain("too weak");
  });
});
