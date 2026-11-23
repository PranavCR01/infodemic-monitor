import { describe, expect, it } from "vitest";
import { checkDuration, checkFile, duration, MAX_BYTES, progressText, rejectionText, timeLeft } from "./rules";

const file = (name: string, size = 1000, type = "video/mp4") => ({ name, size, type });

describe("checkFile", () => {
  it("accepts MP4 and MOV, by type or by extension", () => {
    expect(checkFile(file("a.mp4"))).toBeNull();
    expect(checkFile(file("a.MOV", 1000, "video/quicktime"))).toBeNull();
    expect(checkFile(file("a.mov", 1000, ""))).toBeNull();
  });

  it("rejects other types, empty files and files over the limit, in plain words", () => {
    expect(checkFile(file("a.avi", 1000, "video/x-msvideo"))?.title).toBe("This file type can't be analysed");
    expect(checkFile(file("a.mp4", 0))?.title).toBe("This file is empty");
    const big = checkFile(file("big.mp4", MAX_BYTES + 1));
    expect(big?.title).toBe("This video is too large to analyse");
    expect(big?.detail).toMatch(/The limit is 100 MB/);
  });
});

describe("checkDuration", () => {
  it("uses the 3-minute limit and says how long the video is", () => {
    expect(checkDuration("clinic-tour.mov", 252)?.detail).toBe("clinic-tour.mov is 4 min 12 s. The limit is 3 minutes. Trim it and upload again.");
    expect(checkDuration("ok.mp4", 180)).toBeNull();
  });

  it("lets an unreadable length through for the server to check", () => {
    expect(checkDuration("x.mp4", null)).toBeNull();
    expect(checkDuration("x.mp4", NaN)).toBeNull();
  });
});

describe("rejectionText", () => {
  it("explains T20's rejection codes, never showing the code", () => {
    expect(rejectionText({ detail: { code: "too_long", message: "200s > 180s" } }, 422)).toBe("The video is longer than 3 minutes.");
    const unknown = rejectionText({ detail: { code: "new_code" } }, 422);
    expect(unknown).not.toContain("new_code");
  });

  it("falls back on the status", () => {
    expect(rejectionText(null, 401)).toMatch(/Sign in again/);
    expect(rejectionText(null, 503)).toMatch(/isn't available/);
  });
});

describe("progress text", () => {
  it("shows MB and time left", () => {
    expect(progressText(11.8 * 1048576, 18.4 * 1048576)).toBe("11.8 of 18.4 MB");
    expect(timeLeft(1000, 2000, 8000)).toBe("About 8 seconds left");
    expect(timeLeft(1000, 100000, 1000)).toBe("About 2 min left");
    expect(timeLeft(0, 1000, 1000)).toBe("");
  });

  it("formats durations", () => {
    expect(duration(42)).toBe("42 s");
    expect(duration(252)).toBe("4 min 12 s");
    expect(duration(180)).toBe("3 minutes");
    expect(duration(60)).toBe("1 minute");
  });
});
