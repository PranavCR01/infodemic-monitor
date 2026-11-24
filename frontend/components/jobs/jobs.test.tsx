import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { adaptJobList, adaptProgress } from "@/lib/api/job-adapter";
import { MOCK_FAILED, MOCK_JOB_PAGE, MOCK_QUEUED, MOCK_RETRYING, MOCK_RUNNING } from "@/lib/api/mocks/jobs";
import { EMPTY_FILTERS } from "@/lib/job-filters";
import { JobProgress } from "./JobProgress";
import { JobsList } from "./JobsList";

const progress = (raw = MOCK_RUNNING, extra: Partial<Parameters<typeof JobProgress>[0]> = {}) =>
  render(<JobProgress filename="hot-water-flu.mp4" jobId={raw.job_id} errorCode={null} progress={adaptProgress(raw)} lost={false} onCheckNow={vi.fn()} {...extra} />);

describe("JobProgress", () => {
  it("announces the current step politely, and names each step's status for screen readers", () => {
    progress();
    expect(screen.getByText("Now: Searching evidence")).toHaveAttribute("aria-live", "polite");
    const steps = screen.getAllByRole("listitem");
    expect(steps[0]).toHaveTextContent("Step 1: Uploaded, done");
    expect(steps[5]).toHaveTextContent("Searching evidence, in progress");
    expect(steps[7]).toHaveTextContent("not started");
  });

  it("shows the retry banner and attempt", () => {
    progress(MOCK_RETRYING);
    expect(screen.getAllByText(/Temporary problem, retrying automatically/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Attempt 2/)).toBeInTheDocument();
  });

  it("explains a failure in plain words, with the step, actions and the job reference", () => {
    progress(MOCK_FAILED, { errorCode: "TRANSCRIPTION_ERROR", onRetry: vi.fn().mockResolvedValue(undefined) });
    expect(screen.getByText(/couldn't transcribe the speech.*It stopped at: Transcribing speech/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry analysis" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload a different file" })).toHaveAttribute("href", "/");
    expect(screen.getByText("job-fail")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("TRANSCRIPTION_ERROR");
    expect(screen.queryByText("You can leave this page")).not.toBeInTheDocument();
  });

  it("says it's waiting while queued", () => {
    progress(MOCK_QUEUED);
    expect(screen.getByRole("heading", { name: "Waiting to start" })).toBeInTheDocument();
  });

  it("offers 'Check now' after a lost connection", () => {
    const onCheckNow = vi.fn();
    progress(MOCK_RUNNING, { lost: true, onCheckNow });
    fireEvent.click(screen.getByRole("button", { name: "Check now" }));
    expect(onCheckNow).toHaveBeenCalled();
  });
});

describe("JobsList", () => {
  const { rows, total } = adaptJobList(MOCK_JOB_PAGE);
  const list = (extra: Partial<Parameters<typeof JobsList>[0]> = {}) =>
    render(<JobsList rows={rows} total={total} filters={EMPTY_FILTERS} onFilters={vi.fn()} error={null} {...extra} />);

  it("lists videos with state, step and label, each linking to its page", () => {
    list();
    const row = screen.getByRole("link", { name: "hot-water-flu.mp4" }).closest("tr")!;
    expect(within(row).getByText("Running")).toBeInTheDocument();
    expect(within(row).getByText("Searching evidence")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "hot-water-flu.mp4" })).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByText("Updating 2 running jobs…")).toBeInTheDocument();
  });

  it("shows loading skeletons, then the right empty state", () => {
    const { unmount } = list({ rows: null });
    expect(screen.getByLabelText("Loading your videos")).toBeInTheDocument();
    unmount();
    const onFilters = vi.fn();
    const { unmount: u2 } = list({ rows: [], onFilters, filters: { ...EMPTY_FILTERS, q: "zzz" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onFilters).toHaveBeenCalledWith(EMPTY_FILTERS);
    u2();
    list({ rows: [] });
    expect(screen.getByText("No videos yet")).toBeInTheDocument();
  });

  it("sends filter changes back to the page, from page 1", () => {
    const onFilters = vi.fn();
    list({ onFilters, filters: { ...EMPTY_FILTERS, page: 3 } });
    fireEvent.change(screen.getByLabelText("State"), { target: { value: "FAILED" } });
    expect(onFilters).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, state: "FAILED", page: 1 });
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: " flu " } });
    fireEvent.submit(screen.getByRole("search"));
    expect(onFilters).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, q: "flu", page: 1 });
  });
});
