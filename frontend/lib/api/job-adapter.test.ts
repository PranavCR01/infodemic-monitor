import { describe, expect, it } from "vitest";
import { adaptJobList, adaptJobRow, adaptProgress, elapsed, failureText } from "./job-adapter";
import { MOCK_DONE, MOCK_FAILED, MOCK_JOB_PAGE, MOCK_QUEUED, MOCK_RETRYING, MOCK_RUNNING, MOCK_SINGLE_CALL } from "./mocks/jobs";

describe("adaptProgress", () => {
  const statuses = (p: ReturnType<typeof adaptProgress>) => p.steps.map((s) => s.status);

  it("marks finished steps done, the current one now, the rest pending, with durations", () => {
    const p = adaptProgress(MOCK_RUNNING);
    expect(statuses(p)).toEqual(["done", "done", "done", "done", "done", "now", "pending", "pending"]);
    expect(p.currentText).toBe("Searching evidence");
    expect(p.steps[1]).toMatchObject({ text: "Transcribing speech", seconds: 12 });
    expect(p.steps[5].seconds).toBeNull();
  });

  it("shows a retry as a warning on the current step, with the attempt", () => {
    const p = adaptProgress(MOCK_RETRYING);
    expect(p.state).toBe("RETRYING");
    expect(p.steps[5].status).toBe("warn");
    expect(p.attempt).toBe(2);
  });

  it("marks the step it failed at", () => {
    const p = adaptProgress(MOCK_FAILED);
    expect(statuses(p).slice(0, 3)).toEqual(["done", "fail", "pending"]);
    expect(p.failedStep).toBe("Transcribing speech");
  });

  it("has nothing in progress while queued", () => {
    const p = adaptProgress(MOCK_QUEUED);
    expect(p.state).toBe("QUEUED");
    expect(statuses(p).every((s) => s === "pending")).toBe(true);
    expect(p.currentText).toBeNull();
  });

  it("marks every step done when finished", () => {
    const p = adaptProgress(MOCK_DONE);
    expect(statuses(p).every((s) => s === "done")).toBe(true);
    expect(p.steps[7].seconds).toBe(3);
  });

  it("shows only the steps this job's pipeline goes through", () => {
    expect(adaptProgress(MOCK_SINGLE_CALL).steps.map((s) => s.key)).toEqual(["uploaded", "transcribing", "verifying", "searching_evidence"]);
  });
});

describe("jobs list", () => {
  it("reads T28's page and today's bare array", () => {
    expect(adaptJobList(MOCK_JOB_PAGE).total).toBe(5);
    const legacy = adaptJobList(MOCK_JOB_PAGE.items.map(({ state, step, ...rest }) => rest));
    expect(legacy.total).toBeNull();
    expect(legacy.rows[2].state).toBe("NEEDS_REVIEW");
  });

  it("prefers T28's finer state, and shows the step only for running jobs", () => {
    const rows = adaptJobList(MOCK_JOB_PAGE).rows;
    expect(rows[0]).toMatchObject({ state: "RUNNING", step: "Searching evidence", active: true });
    expect(rows[1]).toMatchObject({ state: "RETRYING", active: true });
    expect(rows[3]).toMatchObject({ state: "COMPLETED", step: null, active: false, label: "DEBUNKING" });
  });

  it("never passes an unknown label through", () => {
    expect(adaptJobRow({ job_id: "x", status: "SUCCESS", label: "WEIRD" }).label).toBeNull();
  });
});

describe("helpers", () => {
  it("formats elapsed time", () => {
    expect(elapsed("2026-11-23T10:00:00Z", Date.parse("2026-11-23T10:01:12Z"))).toBe("1:12");
    expect(elapsed(null)).toBe("");
  });

  it("explains failures in plain language, never the code", () => {
    expect(failureText("TRANSCRIPTION_ERROR")).toMatch(/transcribe/);
    expect(failureText("NEW_CODE")).not.toContain("NEW_CODE");
  });
});

describe("T30 basis and long timers", () => {
  it("shows MISINFO (unproven) in the list from misinfo_basis, only on MISINFO", () => {
    expect(adaptJobRow({ job_id: "a", status: "REVIEW_REQUIRED", label: "MISINFO", misinfo_basis: "unproven" }).basis).toBe("unproven");
    expect(adaptJobRow({ job_id: "b", status: "SUCCESS", label: "DEBUNKING", misinfo_basis: "unproven" }).basis).toBeNull();
    expect(adaptJobRow({ job_id: "c", status: "SUCCESS", label: "MISINFO", misinfo_basis: "weird" }).basis).toBeNull();
  });

  it("switches to hours past an hour and days past a day", () => {
    const t0 = "2026-11-23T00:00:00Z";
    expect(elapsed(t0, Date.parse("2026-11-23T00:59:59Z"))).toBe("59:59");
    expect(elapsed(t0, Date.parse("2026-11-23T02:05:09Z"))).toBe("2:05:09");
    expect(elapsed(t0, Date.parse("2026-11-26T04:30:00Z"))).toBe("3 d 4 h");
  });
});
