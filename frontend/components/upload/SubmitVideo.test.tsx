import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UploadError } from "@/lib/upload/flow";
import { SubmitVideo, type UploadDeps } from "./SubmitVideo";

const video = (name = "hot-water-flu.mp4", size = 18 * 1048576, type = "video/mp4") => new File([new Uint8Array(1)], name, { type }) as File & { size: number };
const sized = (f: File, size: number) => Object.defineProperty(f, "size", { value: size });

function setup(over: Partial<UploadDeps> = {}) {
  const deps: UploadDeps = {
    readDuration: vi.fn().mockResolvedValue(42),
    uploadVideo: vi.fn().mockResolvedValue({ videoId: "v1", duplicate: false }),
    startAnalysis: vi.fn().mockResolvedValue("job-9"),
    goToJob: vi.fn(),
    ...over,
  };
  render(<SubmitVideo deps={deps} />);
  const choose = async (f: File) => {
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/choose a file/i), { target: { files: [f] } });
    });
  };
  return { deps, choose };
}

describe("SubmitVideo", () => {
  it("states the limits, and shows 'Paste a link' as coming soon", () => {
    setup();
    expect(screen.getByText("MP4 or MOV · up to 100 MB · up to 3 minutes")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Paste a link/ })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "Start analysis" })).toBeDisabled();
  });

  it("uploads, then starts the analysis and goes to its page", async () => {
    const { deps, choose } = setup();
    await choose(sized(video(), 18 * 1048576));
    expect(await screen.findByText("Uploaded.")).toBeInTheDocument();
    expect(screen.getByText(/18\.0 MB · 42 s/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));
    await waitFor(() => expect(deps.goToJob).toHaveBeenCalledWith("job-9"));
    expect(deps.startAnalysis).toHaveBeenCalledWith("v1");
  });

  it("refuses a video over 3 minutes before uploading anything", async () => {
    const { deps, choose } = setup({ readDuration: vi.fn().mockResolvedValue(252) });
    await choose(video("clinic-tour.mov", 1000, "video/quicktime"));
    expect(await screen.findByText("This video is too long to analyse")).toBeInTheDocument();
    expect(screen.getByText(/clinic-tour\.mov is 4 min 12 s\. The limit is 3 minutes\. .*Nothing was uploaded\./)).toBeInTheDocument();
    expect(deps.uploadVideo).not.toHaveBeenCalled();
  });

  it("refuses the wrong type and a file over 100 MB without reading it", async () => {
    const { deps, choose } = setup();
    await choose(video("notes.pdf", 1000, "application/pdf"));
    expect(await screen.findByText("This file type can't be analysed")).toBeInTheDocument();
    await choose(sized(video("big.mp4"), 101 * 1048576));
    expect(await screen.findByText("This video is too large to analyse")).toBeInTheDocument();
    expect(deps.readDuration).not.toHaveBeenCalled();
  });

  it("shows progress with MB, and Cancel returns to the start", async () => {
    let progress: (s: number, t: number) => void = () => {};
    let signal: AbortSignal | null = null;
    const { choose } = setup({
      uploadVideo: vi.fn((_f, onProgress, s) => {
        progress = onProgress;
        signal = s;
        return new Promise<never>((_, reject) => s.addEventListener("abort", () => reject(new UploadError("Upload cancelled.", true))));
      }),
    });
    await choose(sized(video(), 18.4 * 1048576));
    await act(async () => progress(11.8 * 1048576, 18.4 * 1048576));
    expect(screen.getByRole("progressbar", { name: "Upload progress" })).toHaveAttribute("aria-valuenow", "64");
    expect(screen.getByText(/Uploading… 11\.8 of 18\.4 MB/)).toBeInTheDocument();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel" })));
    expect(signal!.aborted).toBe(true);
    expect(screen.getByText(/Drag a video here/)).toBeInTheDocument();
  });

  it("explains a failed upload and offers another file", async () => {
    const { choose } = setup({ uploadVideo: vi.fn().mockRejectedValue(new UploadError("The video is longer than 3 minutes.")) });
    await choose(video());
    expect(await screen.findByText("The upload stopped")).toBeInTheDocument();
    expect(screen.getByText(/longer than 3 minutes/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose another file" })).toBeInTheDocument();
  });

  it("says when the same video was submitted before", async () => {
    const { choose } = setup({ uploadVideo: vi.fn().mockResolvedValue({ videoId: "v1", duplicate: true }) });
    await choose(video());
    expect(await screen.findByText(/submitted before/)).toBeInTheDocument();
  });
});
