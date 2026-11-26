import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_MISINFO_PENDING, MOCK_OLDER_VERSION, MOCK_REANALYSED } from "@/lib/api/mocks/results";
import { mayReanalyse } from "@/lib/hooks/useViewerId";
import { toReviewStatus } from "@/lib/vocabulary";
import { ResultView } from "./ResultView";

describe("versions in the result adapter (T55)", () => {
  it("keeps previous analyses newest first, marks rejected ones and reads the basis", () => {
    const v = adaptResult(MOCK_REANALYSED).versions;
    expect(v.previous.map((p) => p.jobId)).toEqual(["mock-job-3a", "mock-job-3z"]);
    expect(v.previous[0]).toMatchObject({ label: "MISINFO", basis: "unproven", pipelineVersion: "graph_v1+1111111+p0000aaaa", rejected: false });
    expect(v.previous[1].rejected).toBe(true);
    expect(v.latest).toEqual({ jobId: "mock-job-3c", running: true, failed: false });
    expect(v.isCurrent).toBe(true);
  });

  it("defaults to current with no versions on results from before T55", () => {
    expect(adaptResult(MOCK_MISINFO_PENDING).versions).toEqual({ previous: [], isCurrent: true, currentJobId: null, latest: null });
  });

  it("reads a failed newer run", () => {
    const v = adaptResult({ ...MOCK_REANALYSED, latest_job: { job_id: "x", status: "FAILED", state: "FAILED" } }).versions;
    expect(v.latest).toEqual({ jobId: "x", running: false, failed: true });
  });
});

describe("superseded review cases (T55)", () => {
  it("map to 'Superseded by a newer analysis', by case_status or status", () => {
    expect(toReviewStatus({ status: "REVIEW_REQUIRED", case_status: "SUPERSEDED" })).toBe("SUPERSEDED");
    expect(toReviewStatus({ status: "SUPERSEDED" })).toBe("SUPERSEDED");
  });

  it("show on the result page with a link to the newer analysis", () => {
    const raw = { ...MOCK_MISINFO_PENDING, review: { ...MOCK_MISINFO_PENDING.review!, case_status: "SUPERSEDED" as const, superseded_by_job_id: "new-job" } };
    render(<ResultView result={adaptResult(raw)} />);
    expect(screen.getByText("Superseded by a newer analysis")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the newer analysis" })).toHaveAttribute("href", "/jobs/new-job");
  });
});

describe("who may re-analyse (T55)", () => {
  it("is the video's owner or an admin, never a reviewer on someone else's video", () => {
    expect(mayReanalyse({ id: "u1", role: "analyst" }, "u1")).toBe(true);
    expect(mayReanalyse({ id: "u2", role: "reviewer" }, "u1")).toBe(false);
    expect(mayReanalyse({ id: "u3", role: "admin" }, "u1")).toBe(true);
    expect(mayReanalyse({ id: "u3", role: "admin" }, null)).toBe(true);
    expect(mayReanalyse(null, "u1")).toBe(false);
    expect(mayReanalyse(undefined, "u1")).toBe(false);
  });
});

describe("Re-analyse button and dialog (T55)", () => {
  it("is absent without the controls", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} />);
    expect(screen.queryByRole("button", { name: "Re-analyse" })).not.toBeInTheDocument();
  });

  it("opens a dialog naming the cost, sends the optional reason and follows the new job", async () => {
    const onReanalyse = vi.fn().mockResolvedValue({ ok: true, jobId: "new-job", remaining: 2 });
    const onStarted = vi.fn();
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} reanalyse={{ onReanalyse, onStarted }} />);
    fireEvent.click(screen.getByRole("button", { name: "Re-analyse" }));
    const dialog = screen.getByRole("dialog", { name: "Re-analyse this video?" });
    expect(dialog).toHaveTextContent("one more analysis");
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Reason/ }), { target: { value: "search improved" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Start re-analysis" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith("new-job"));
    expect(onReanalyse).toHaveBeenCalledWith("search improved");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the dialog open with the reason when the server refuses (e.g. the rate limit)", async () => {
    const onReanalyse = vi.fn().mockResolvedValue({ ok: false, message: "You can re-analyse it again in about 2 hours." });
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} reanalyse={{ onReanalyse, onStarted: vi.fn() }} />);
    fireEvent.click(screen.getByRole("button", { name: "Re-analyse" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Start re-analysis" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("in about 2 hours");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Previous analyses and version notices (T55)", () => {
  it("lists earlier analyses newest first with their version, marks the current one, and links only openable ones", () => {
    render(<ResultView result={adaptResult(MOCK_REANALYSED)} />);
    const list = screen.getByRole("heading", { name: "Previous analyses" }).closest("section")!;
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(/This analysis\s*Current/);
    expect(items[1]).toHaveTextContent("graph_v1+1111111+p0000aaaa");
    expect(within(items[1]).getByRole("link")).toHaveAttribute("href", "/jobs/mock-job-3a");
    expect(items[2]).toHaveTextContent("rejected by a reviewer");
    expect(within(items[2]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("says when a newer analysis is running, with a link to follow it", () => {
    render(<ResultView result={adaptResult(MOCK_REANALYSED)} />);
    expect(screen.getByText(/A new analysis of this video is running/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Follow its progress" })).toHaveAttribute("href", "/jobs/mock-job-3c");
  });

  it("says when this is an older analysis, linking to the current result", () => {
    render(<ResultView result={adaptResult(MOCK_OLDER_VERSION)} />);
    expect(screen.getByText(/This is an older analysis of this video/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the current result" })).toHaveAttribute("href", "/jobs/mock-job-3b");
  });
});
