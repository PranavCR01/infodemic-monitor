import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { adaptCase } from "@/lib/api/review-adapter";
import type { RawCase } from "@/lib/api/review-types";
import { MOCK_MISINFO_PENDING, MOCK_UNPROVEN } from "@/lib/api/mocks/results";
import { adaptBlindMaterial, type BlindMaterial } from "@/lib/api/blind-material";
import { MOCK_BLIND_MATERIAL } from "@/lib/api/mocks/blind-material";
import { MOCK_CASE_DECIDED, MOCK_CASE_HIGH, MOCK_CASE_NORMAL, MOCK_CASE_OWN, MOCK_VIEWER_ID, mockRevealed } from "@/lib/api/mocks/reviews";
import { ReviewWorkspace } from "./ReviewWorkspace";

const result = adaptResult(MOCK_MISINFO_PENDING);

/** Stands in for WorkspaceClient: on a saved pre-reveal, the server's revealed case replaces the old one. */
const BLIND = adaptBlindMaterial(MOCK_BLIND_MATERIAL);

function Harness({ raw, onDecide, onPreReveal, blind = BLIND, blindFailed = false, videoUrl = null }: {
  raw: RawCase;
  onDecide: ReturnType<typeof vi.fn>;
  onPreReveal: ReturnType<typeof vi.fn>;
  blind?: BlindMaterial | null;
  blindFailed?: boolean;
  videoUrl?: string | null;
}) {
  const [c, setC] = useState(raw);
  return (
    <ReviewWorkspace
      review={adaptCase(c, MOCK_VIEWER_ID)}
      result={result}
      blindMaterial={blind}
      blindMaterialFailed={blindFailed}
      videoUrl={videoUrl}
      onDecide={onDecide}
      onPreReveal={async (body) => {
        const r = await onPreReveal(body);
        if (r.ok) setC(mockRevealed(body.claims));
        return r;
      }}
      onOverrideSeverity={vi.fn().mockResolvedValue({ ok: true })}
    />
  );
}

const setup = (raw: RawCase = MOCK_CASE_HIGH, onDecide = vi.fn().mockResolvedValue({ ok: true }), onPreReveal = vi.fn().mockResolvedValue({ ok: true })) => {
  render(<Harness raw={raw} onDecide={onDecide} onPreReveal={onPreReveal} />);
  return { onDecide, onPreReveal };
};
const choose = (label: string | RegExp, value: string) => fireEvent.change(screen.getByRole("combobox", { name: label }), { target: { value } });
const note = () => screen.getByRole("textbox", { name: /^Note/ });
const judgeAll = () => {
  for (const id of ["c1", "c2", "c3"]) {
    fireEvent.change(document.getElementById(`mine-st-${id}`)!, { target: { value: "ENDORSES" } });
    fireEvent.change(document.getElementById(`mine-v-${id}`)!, { target: { value: "INSUFFICIENT_EVIDENCE" } });
  }
};

describe("ReviewWorkspace: HIGH priority (judgement first, run by the server since T34)", () => {
  it("hides the system's label, verdicts and reasons while the server withholds them", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Your judgement first" })).toBeInTheDocument();
    expect(screen.queryByText("System label:")).not.toBeInTheDocument();
    expect(screen.queryByText("Contradicted by evidence", { ignore: "option, script, style" })).not.toBeInTheDocument();
    expect(screen.queryByText(/A false claim is mentioned/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open the full result" })).not.toBeInTheDocument();
    expect(screen.queryByText("Decided the label")).not.toBeInTheDocument();
    // each claim is shown as stated
    expect(screen.getAllByText(/Drinking hot water every hour/).length).toBeGreaterThan(0);
  });

  it("shows T40's quotes and sources before the reveal, but never whether a source supports or contradicts", () => {
    setup();
    expect(screen.getAllByText(/Hot drinks and symptom relief/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/That's it, that's the secret/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Contradicts")).not.toBeInTheDocument();
    expect(screen.queryByText("Supports")).not.toBeInTheDocument();
    expect(screen.getByText(/Whether each source supports or contradicts the claim/)).toBeInTheDocument();
  });

  it("says when the blind material is loading or couldn't be loaded, and still lists the claims", () => {
    const { unmount } = render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} blind={null} />);
    expect(screen.getByText("Loading the quotes and sources…")).toBeInTheDocument();
    unmount();
    render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} blind={null} blindFailed />);
    expect(screen.getByText(/quotes and sources couldn't be loaded/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Claim 3" })).toBeInTheDocument();
  });

  it("asks for a judgement on every claim the case lists, not only the deciding one", () => {
    setup();
    for (const n of [1, 2, 3]) expect(screen.getByRole("group", { name: `Claim ${n}` })).toBeInTheDocument();
    const commit = screen.getByRole("button", { name: "Commit and show system assessment" });
    fireEvent.change(document.getElementById("mine-st-c1")!, { target: { value: "ENDORSES" } });
    fireEvent.change(document.getElementById("mine-v-c1")!, { target: { value: "CONTRADICTED" } });
    expect(commit).toBeDisabled();
    judgeAll();
    expect(commit).toBeEnabled();
  });

  it("sends T34's pre-reveal body, then shows the server's revealed case and the comparison", async () => {
    const { onPreReveal } = setup();
    judgeAll();
    fireEvent.click(screen.getByRole("button", { name: "Commit and show system assessment" }));
    await waitFor(() => expect(onPreReveal).toHaveBeenCalledTimes(1));
    expect(onPreReveal.mock.calls[0][0]).toEqual({
      claims: ["c1", "c2", "c3"].map((id) => ({ claim_id: id, stance: "ENDORSES", verdict: "INSUFFICIENT_EVIDENCE" })),
    });
    expect(await screen.findByRole("heading", { name: "You and the system" })).toBeInTheDocument();
    expect(screen.getByText(/You and the system disagree on claim 1, claim 2/)).toBeInTheDocument();
    expect(screen.getByText("System label:")).toBeInTheDocument();
    expect(screen.getByText("Decided the label")).toBeInTheDocument();
    expect(screen.getAllByText(/Hot drinks and symptom relief/).length).toBeGreaterThan(0);
    // the recorded judgement can't be changed afterwards, and still shows what was chosen
    expect(document.getElementById("mine-st-c1")).toBeDisabled();
    expect(document.getElementById("mine-st-c1")).toHaveValue("ENDORSES");
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeEnabled();
  });

  it("keeps the choices and says why when the server refuses the judgement", async () => {
    setup(MOCK_CASE_HIGH, undefined, vi.fn().mockResolvedValue({ ok: false, message: "Give a stance and a verdict for every claim, then try again." }));
    judgeAll();
    fireEvent.click(screen.getByRole("button", { name: "Commit and show system assessment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/every claim/);
    expect(screen.queryByText("System label:")).not.toBeInTheDocument();
    expect(document.getElementById("mine-v-c3")).toHaveValue("INSUFFICIENT_EVIDENCE");
  });

  it("doesn't allow a decision before the reveal", () => {
    setup();
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeDisabled();
  });
});

describe("ReviewWorkspace: decision form", () => {
  const normal = MOCK_CASE_NORMAL;

  it("shows the system assessment straight away on non-HIGH cases", () => {
    setup(normal);
    expect(screen.queryByRole("heading", { name: "Your judgement first" })).not.toBeInTheDocument();
    expect(screen.getByText("System label:")).toBeInTheDocument();
  });

  it("refuses to submit without a decision, a reason and a note", async () => {
    const { onDecide } = setup(normal);
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    expect(await screen.findByText("Choose a decision.")).toBeInTheDocument();
    expect(screen.getByText("Choose a reason.")).toBeInTheDocument();
    expect(screen.getByText(/at least 10 characters/)).toBeInTheDocument();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("sends a complete approval as T34's request body", async () => {
    const { onDecide } = setup(normal);
    fireEvent.click(screen.getByRole("radio", { name: /Approve the label/ }));
    choose(/^Reason/, "SYSTEM_CORRECT");
    fireEvent.change(note(), { target: { value: "Both sources contradict the claim." } });
    fireEvent.click(screen.getByRole("button", { name: "Approve label" }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledTimes(1));
    expect(onDecide.mock.calls[0][0].body).toEqual({
      action: "APPROVE",
      reason: "Both sources contradict the claim.",
      reason_code: "SYSTEM_CORRECT",
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
    choose(/^Reason/, "OTHER");
    fireEvent.change(note(), { target: { value: "Audio is music only." } });
    fireEvent.click(screen.getByRole("button", { name: "Reject result" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Someone else decided/);
    expect(note()).toHaveValue("Audio is music only.");
  });
});

describe("ReviewWorkspace: how we searched (T52)", () => {
  it("gives the plain finding, with the raw critic notes and every query behind Technical details", () => {
    setup(MOCK_CASE_NORMAL);
    const sections = screen.getAllByRole("region", { name: "How we searched" });
    expect(sections).toHaveLength(3);
    expect(sections[2]).toHaveTextContent(/No relevant study was found after 2 searches/);
    const tech = within(sections[2]).getByText("Technical details").closest("details")!;
    expect(tech).not.toHaveAttribute("open");
    expect(within(tech).getAllByText("vitamin C prevention infection")).toHaveLength(2);
    expect(within(tech).getByText(/repeated, not counted again/)).toBeInTheDocument();
    const first = within(sections[0]).getByText("Technical details").closest("details")!;
    expect(within(first).getByText(/The trial population was adults with common cold/)).toBeInTheDocument();
  });

  it("says nothing about the search during the blind step", () => {
    setup();
    expect(screen.queryByRole("region", { name: "How we searched" })).not.toBeInTheDocument();
    expect(screen.queryByText("Technical details")).not.toBeInTheDocument();
  });
});

describe("ReviewWorkspace: fewer sources on screen (T59)", () => {
  const ref = (i: number) => ({ evidence_id: `p${i}`, source_kind: "pubmed" as const, rank: i, title: `Retrieved paper ${i}`, study_type: "rct" });
  const many = adaptBlindMaterial({
    ...MOCK_BLIND_MATERIAL,
    claims: MOCK_BLIND_MATERIAL.claims!.map((c, k) => (k === 0 ? { ...c, references: [1, 2, 3, 4, 5, 6].map(ref) } : c)),
  });

  it("shows the top 3 in retrieval order in the blind step, the rest behind a button, with no relation hints", () => {
    render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} blind={many} />);
    const claim1 = screen.getByRole("article", { name: "Claim 1" });
    expect(within(claim1).getAllByText(/Retrieved paper \d/).map((e) => e.textContent)).toEqual(["Retrieved paper 1", "Retrieved paper 2", "Retrieved paper 3"]);
    fireEvent.click(within(claim1).getByRole("button", { name: "Show 3 more sources" }));
    expect(within(claim1).getAllByText(/Retrieved paper \d/).map((e) => e.textContent)).toEqual([1, 2, 3, 4, 5, 6].map((i) => `Retrieved paper ${i}`));
    expect(within(claim1).queryByText(/Contradicts|Supports/)).not.toBeInTheDocument();
  });

  it("after the reveal, puts the cited sources first and collapses the rest beyond 3", () => {
    const withUnused = {
      ...MOCK_MISINFO_PENDING,
      claims: [
        {
          ...MOCK_MISINFO_PENDING.claims![0],
          evidence: [
            { evidence_id: "u1", title: "Unused paper A", relation: "CONSIDERED", source_kind: "pubmed" as const, study_type: "rct" },
            ...MOCK_MISINFO_PENDING.claims![0].evidence!,
            { evidence_id: "u2", title: "Unused paper B", relation: "CONSIDERED", source_kind: "pubmed" as const, study_type: "rct" },
            { evidence_id: "u3", title: "Unused paper C", relation: "CONSIDERED", source_kind: "pubmed" as const, study_type: "rct" },
          ],
        },
        ...MOCK_MISINFO_PENDING.claims!.slice(1),
      ],
    };
    render(
      <ReviewWorkspace review={adaptCase(MOCK_CASE_NORMAL, MOCK_VIEWER_ID)} result={adaptResult(withUnused)} onDecide={vi.fn()} onPreReveal={vi.fn()} onOverrideSeverity={vi.fn()} />,
    );
    const claim1 = screen.getByRole("article", { name: "Claim 1" });
    const titles = () => within(claim1).getAllByRole("heading", { level: 4 }).map((h) => h.textContent).filter((t) => t && !/^(What|How)/i.test(t));
    // the 2 cited sources first, then the first unused one; 2 more behind the button
    expect(titles()).toHaveLength(3);
    expect(titles()[2]).toBe("Unused paper A");
    expect(within(claim1).getAllByText("Contradicts")).toHaveLength(2);
    fireEvent.click(within(claim1).getByRole("button", { name: "Show 2 more sources" }));
    expect(titles().slice(3)).toEqual(["Unused paper B", "Unused paper C"]);
  });
});

describe("ReviewWorkspace: video (T56)", () => {
  const URL_ = "https://storage.example/signed/video.mp4?token=x";
  const video = () => document.querySelector("video") as HTMLVideoElement | null;

  it("shows the player to a reviewer on another user's case, already in the blind step", () => {
    // rev-1 was submitted by someone else (OTHER_A); the viewer is a reviewer judging it blind.
    render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} videoUrl={URL_} />);
    expect(screen.getByRole("heading", { name: "Your judgement first" })).toBeInTheDocument();
    expect(video()).toHaveAttribute("src", URL_);
    expect(screen.queryByText("System label:")).not.toBeInTheDocument();
  });

  it("seeks the video from a claim's time range and from a quoted line, by keyboard-reachable buttons", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} videoUrl={URL_} />);
    fireEvent.click(screen.getByRole("button", { name: /play claim 2/ }));
    expect(video()!.currentTime).toBeCloseTo(8.1);
    fireEvent.click(screen.getAllByRole("button", { name: /That's it, that's the secret.*play from 0:03/ })[0]);
    expect(video()!.currentTime).toBeCloseTo(3.2);
    expect(play).toHaveBeenCalledTimes(2);
    play.mockRestore();
  });

  it("keeps the player and seeking after the reveal", () => {
    render(<Harness raw={MOCK_CASE_NORMAL} onDecide={vi.fn()} onPreReveal={vi.fn()} videoUrl={URL_} />);
    expect(video()).not.toBeNull();
    expect(screen.getByRole("button", { name: /play claim 1/ })).toBeInTheDocument();
  });

  it("says when there's no playable video, and shows times as plain text", () => {
    render(<Harness raw={MOCK_CASE_HIGH} onDecide={vi.fn()} onPreReveal={vi.fn()} videoUrl={null} />);
    expect(video()).toBeNull();
    expect(screen.getByText(/Video playback isn't available for this video/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play claim/ })).not.toBeInTheDocument();
  });
});

describe("ReviewWorkspace: superseded case (T55)", () => {
  it("says the case was superseded, links the newer analysis and can't be decided", () => {
    setup({ ...MOCK_CASE_NORMAL, status: "SUPERSEDED", superseded_by_job_id: "new-job" });
    expect(screen.getByText("Superseded by a newer analysis.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the newer analysis" })).toHaveAttribute("href", "/jobs/new-job");
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeDisabled();
  });
});

describe("ReviewWorkspace: read-only cases", () => {
  it("doesn't let reviewers decide their own submission", () => {
    setup({ ...MOCK_CASE_OWN, severity: "MEDIUM", blind_step_required: false, system_view_withheld: false });
    expect(screen.getByText("Your submission. Another reviewer decides.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save decision" })).toBeDisabled();
  });

  it("shows who decided a resolved case, by name, and locks the form", () => {
    render(
      <ReviewWorkspace review={adaptCase(MOCK_CASE_DECIDED, MOCK_VIEWER_ID)} result={adaptResult(MOCK_UNPROVEN)} onDecide={vi.fn()} onPreReveal={vi.fn()} onOverrideSeverity={vi.fn()} />,
    );
    const decision = screen.getByRole("region", { name: "Decision" });
    expect(within(decision).getByText(/Approved by Dr. B. Osei/)).toBeInTheDocument();
    expect(within(decision).getByText("Reason: The system's assessment is right")).toBeInTheDocument();
    expect(within(decision).getByText("No study supports sea moss for thyroid disease.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Approve the label/ })).toBeDisabled();
    expect(screen.getByText("Entries can't be edited or removed.")).toBeInTheDocument();
  });
});
