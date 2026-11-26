import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adaptEvals } from "@/lib/api/evals-adapter";
import { MOCK_EVALS } from "@/lib/api/mocks/evals";
import { EvalsList } from "./EvalsList";

const runs = adaptEvals(MOCK_EVALS).runs;
const cards = () => screen.queryAllByRole("article");
const card = (metric: string) => screen.getByRole("article", { name: metric });

describe("EvalsList (T63)", () => {
  it("lists every result, grouped by pipeline step in pipeline order", () => {
    render(<EvalsList runs={runs} />);
    expect(cards()).toHaveLength(6);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.firstChild?.textContent)).toEqual([
      "Find health claims",
      "Rank the evidence",
      "Check claims against evidence",
      "Decide the video's label",
    ]);
  });

  it("shows every field of a record", () => {
    render(<EvalsList runs={runs} />);
    const c = card("verification_macro_f1");
    for (const text of [
      "T38-verify_claims-claude-opus-5-5",
      "0.6759",
      "origin/data/golden-label-set@0fbc68a05a7d",
      "claude-opus-5-5",
      "verify_v3",
      "174",
      "$5.99",
      /No 95% CI/,
    ])
      expect(within(c).getAllByText(text).length).toBeGreaterThan(0);
    expect(within(c).getByText(/24 Nov 2026/)).toBeInTheDocument();
    const link = within(c).getByRole("link", { name: /evals\/reports\/T38_routing\/combined\/report\.md/ });
    expect(link).toHaveAttribute("href", expect.stringMatching(/^https:\/\/github\.com\/.+report\.md$/));
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("labels every tune-split result as development numbers", () => {
    render(<EvalsList runs={runs} />);
    for (const m of ["verification_macro_f1", "claim_f1_strict"])
      expect(within(card(m)).getByText("Development (tune split): not product accuracy")).toBeInTheDocument();
    expect(within(card("unsupported_recall")).queryByText(/tune split/)).not.toBeInTheDocument();
    expect(within(card("unsupported_recall")).getByText("Held-out test split")).toBeInTheDocument();
  });

  it("marks synthetic results clearly, and only those", () => {
    render(<EvalsList runs={runs} />);
    expect(within(card("precision_at_5_strict")).getByText(/Synthetic data: shows how it works, not real accuracy/)).toBeInTheDocument();
    expect(document.querySelectorAll("[data-synthetic]")).toHaveLength(1);
  });

  it("shows the 95% CI only when the record has one", () => {
    render(<EvalsList runs={runs} />);
    expect(screen.getAllByTestId("ci")).toHaveLength(1);
    expect(within(card("claim_f1_strict")).getByTestId("ci")).toHaveTextContent("95% CI 0.586 to 0.761");
    expect(within(card("claim_f1_strict")).getByText("bootstrap over videos, 1000 resamples")).toBeInTheDocument();
    expect(within(card("verification_macro_f1")).queryByTestId("ci")).not.toBeInTheDocument();
  });

  it("says when a cost covers a whole run shared by several results", () => {
    render(<EvalsList runs={runs} />);
    expect(within(card("unsupported_recall")).getByText(/for the whole run, shared by 2 results/)).toBeInTheDocument();
    expect(within(card("verification_macro_f1")).queryByText(/shared by/)).not.toBeInTheDocument();
    expect(within(card("precision_at_5_strict")).getByText("$0 (no paid calls)")).toBeInTheDocument();
  });

  it("doesn't link a report whose URL isn't http(s)", () => {
    render(<EvalsList runs={runs} />);
    expect(within(card("unsupported_recall")).queryByRole("link")).not.toBeInTheDocument();
    expect(within(card("unsupported_recall")).getByText("evals/reports/fixture.md")).toBeInTheDocument();
  });

  it("filters by task, step and split, and clears", () => {
    render(<EvalsList runs={runs} />);
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "T38" } });
    expect(cards().map((c) => c.getAttribute("aria-labelledby"))).toEqual(["eval-T38-verify_claims-claude-opus-5-5"]);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 6 results");

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    fireEvent.change(screen.getByLabelText("Pipeline step"), { target: { value: "verify_claims" } });
    expect(cards()).toHaveLength(3);
    fireEvent.change(screen.getByLabelText("Split"), { target: { value: "test" } });
    expect(cards()).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "T05" } });
    expect(cards()).toHaveLength(0);
    expect(screen.getByText("No results match these filters")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(cards()).toHaveLength(6);
    expect(screen.getByRole("status")).toHaveTextContent("6 results");
  });

  it("filters to results that aren't one golden split", () => {
    render(<EvalsList runs={runs} />);
    fireEvent.change(screen.getByLabelText("Split"), { target: { value: "none" } });
    expect(cards().map((c) => c.getAttribute("aria-labelledby"))).toEqual(["eval-T05-rerank-precision_at_5-reranked", "eval-T24-judge_crosscheck-label_agreement"]);
  });

  it("sorts by date, newest first, without step groups", () => {
    render(<EvalsList runs={runs} />);
    fireEvent.change(screen.getByLabelText("Order"), { target: { value: "newest" } });
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(0);
    expect(cards().map((c) => c.getAttribute("aria-labelledby"))).toEqual([
      "eval-FIXTURE-verify-test-precision",
      "eval-FIXTURE-verify-test-recall",
      "eval-T38-verify_claims-claude-opus-5-5",
      "eval-T43-extraction_ceiling-claim_f1_strict",
      "eval-T24-judge_crosscheck-label_agreement",
      "eval-T05-rerank-precision_at_5-reranked",
    ]);
  });

  it("shows an empty state when nothing is recorded", () => {
    render(<EvalsList runs={[]} />);
    expect(screen.getByText("No evaluations recorded yet")).toBeInTheDocument();
    expect(screen.queryByLabelText("Task")).not.toBeInTheDocument();
  });
});
