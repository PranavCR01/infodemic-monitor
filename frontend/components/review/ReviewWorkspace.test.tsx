import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { adaptCase } from "@/lib/api/review-adapter";
import { MOCK_MISINFO_PENDING, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { MOCK_CASE_DECIDED, MOCK_CASE_HIGH, MOCK_CASE_OWN } from "@/lib/api/mocks/reviews";
import { ReviewWorkspace } from "./ReviewWorkspace";

const result = adaptResult(MOCK_MISINFO_PENDING);
const setup = (raw = MOCK_CASE_HIGH, onDecide = vi.fn().mockResolvedValue({ ok: true })) => {
  render(<ReviewWorkspace review={adaptCase(raw)} result={result} onDecide={onDecide} onOverrideSeverity={vi.fn().mockResolvedValue({ ok: true })} />);
  return onDecide;
};
const choose = (label: string | RegExp, value: string) => fireEvent.change(screen.getByRole("combobox", { name: label }), { target: { value } });
const note = () => screen.getByRole("textbox", { name: /^Note/ });

describe("ReviewWorkspace: HIGH priority (judgement first)", () => {
  it("hides the system's label, verdicts and reasons until the reviewer commits", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Your judgement first" })).toBeInTheDocument();
    expect(screen.queryByText("System label:")).not.toBeInTheDocument();
    expect(screen.queryByText("Contradicted by evidence", { ignore: "option, script, style" })).not.toBeInTheDocument();
    expect(screen.queryByText(/A false claim is mentioned/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open the full result" })).not.toBeInTheDocument();
    // the evidence itself is shown first
    expect(screen.getAllByText(/Drinking hot water every hour/).length).toBeGreaterThan(0);
  });

  it("keeps Commit disabled until every deciding claim has a stance and a verdict, then reveals and compares", () => {
    setup();
    const commit = screen.getByRole("button", { name: "Commit and show system assessment" });
    expect(commit).toBeDisabled();
    choose("The speaker", "ENDORSES");
    expect(commit).toBeDisabled();
    choose("The evidence", "INSUFFICIENT_EVIDENCE");
    expect(commit).toBeEnabled();
    fireEvent.click(commit);
    expect(screen.getByRole("heading", { name: "You and the system" })).toBeInTheDocument();
    expect(screen.getByText(/You and the system disagree on claim 1/)).toBeInTheDocument();
    expect(screen.getByText("System label:")).toBeInTheDocument();
    // the committed judgement can't be changed afterwards
    expect(screen.getByRole("combobox", { name: "The speaker" })).toBeDisabled();
  });

  it("doesn't allow a decision before the reveal", () => {
    setup();
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeDisabled();
  });
});

describe("ReviewWorkspace: decision form", () => {
  const normal = { ...MOCK_CASE_HIGH, severity: "MEDIUM" };

  it("shows the system assessment straight away on non-HIGH cases", () => {
    setup(normal);
    expect(screen.queryByRole("heading", { name: "Your judgement first" })).not.toBeInTheDocument();
    expect(screen.getByText("System label:")).toBeInTheDocument();
  });

  it("refuses to submit without a decision, a reason and a note", async () => {
    const onDecide = setup(normal);
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    expect(await screen.findByText("Choose a decision.")).toBeInTheDocument();
    expect(screen.getByText("Choose a reason.")).toBeInTheDocument();
    expect(screen.getByText(/at least 10 characters/)).toBeInTheDocument();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("sends a complete approval as T27's request body", async () => {
    const onDecide = setup(normal);
    fireEvent.click(screen.getByRole("radio", { name: /Approve the label/ }));
    choose(/^Reason/, "SYSTEM_CORRECT");
    fireEvent.change(note(), { target: { value: "Both sources contradict the claim." } });
    fireEvent.click(screen.getByRole("button", { name: "Approve label" }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledTimes(1));
    expect(onDecide.mock.calls[0][0].body).toEqual({
      action: "APPROVE",
      reason: "[SYSTEM_CORRECT] Both sources contradict the claim.",
      corrected_label: null,
      claim_corrections: [],
    });
    expect(await screen.findByText(/Decision saved/)).toBeInTheDocument();
  });

  it("asks for a new label to correct, and warns (without blocking) when it doesn't follow from the claims", () => {
    setup(normal);
    fireEvent.click(screen.getByRole("radio", { name: /Correct it/ }));
    fireEvent.click(screen.getByRole("radio", { name: /DEBUNKED/ }));
    expect(screen.getByText(/doesn't follow from the claims/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save correction" })).toBeEnabled();
  });

  it("shows the server's refusal and keeps the form", async () => {
    setup(normal, vi.fn().mockResolvedValue({ ok: false, message: "Someone else decided this case while you were working on it." }));
    fireEvent.click(screen.getByRole("radio", { name: /Reject the result/ }));
    choose(/^Reason/, "UNUSABLE_INPUT");
    fireEvent.change(note(), { target: { value: "Audio is music only." } });
    fireEvent.click(screen.getByRole("button", { name: "Reject result" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Someone else decided/);
    expect(note()).toHaveValue("Audio is music only.");
  });
});

describe("ReviewWorkspace: read-only cases", () => {
  it("doesn't let reviewers decide their own submission", () => {
    setup({ ...MOCK_CASE_OWN, severity: "MEDIUM" });
    expect(screen.getByText("Your submission. Another reviewer decides.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save decision" })).toBeDisabled();
  });

  it("shows who decided a resolved case, by name, and locks the form", () => {
    render(
      <ReviewWorkspace review={adaptCase({ ...MOCK_CASE_DECIDED, severity: "MEDIUM" })} result={adaptResult(MOCK_UNPROVEN)} onDecide={vi.fn()} onOverrideSeverity={vi.fn()} />,
    );
    const decision = screen.getByRole("region", { name: "Decision" });
    expect(within(decision).getByText(/Approved by Dr. B. Osei/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeDisabled();
    expect(screen.getByText("Entries can't be edited or removed.")).toBeInTheDocument();
  });
});
