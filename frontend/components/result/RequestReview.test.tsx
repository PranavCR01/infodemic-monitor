import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { adaptResult } from "@/lib/api/result-adapter";
import { MOCK_MISINFO_PENDING, MOCK_NO_CLAIMS } from "@/lib/api/mocks/results";
import { ResultView } from "./ResultView";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(window.location.search) }));
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as never;
});

describe("Request review on the result page (T32)", () => {
  it("is offered only when nobody has been asked to check the result", () => {
    const onRequest = vi.fn();
    const { unmount } = render(<ResultView result={adaptResult(MOCK_NO_CLAIMS)} onRequestReview={onRequest} />);
    expect(screen.getByRole("button", { name: /Request review/ })).toBeInTheDocument();
    unmount();
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} onRequestReview={onRequest} />);
    expect(screen.queryByRole("button", { name: /Request review/ })).not.toBeInTheDocument();
  });

  it("needs a note, sends it, and says the label is now provisional", async () => {
    const onRequest = vi.fn().mockResolvedValue({ ok: true, created: true });
    render(<ResultView result={adaptResult(MOCK_NO_CLAIMS)} onRequestReview={onRequest} />);
    fireEvent.click(screen.getByRole("button", { name: /Request review/ }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send to a reviewer" })));
    expect(screen.getByRole("alert")).toHaveTextContent(/Say what looks wrong/);
    expect(onRequest).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/What should a reviewer check/), { target: { value: "The stretch advice is fine but check the end." } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send to a reviewer" })));
    expect(onRequest).toHaveBeenCalledWith("The stretch advice is fine but check the end.");
    expect(screen.getByText(/Review requested\. Treat the label as provisional/)).toBeInTheDocument();
  });

  it("keeps the note when sending fails", async () => {
    const onRequest = vi.fn().mockResolvedValue({ ok: false, message: "The request couldn't be sent: no connection. Your note is still here." });
    render(<ResultView result={adaptResult(MOCK_NO_CLAIMS)} onRequestReview={onRequest} />);
    fireEvent.click(screen.getByRole("button", { name: /Request review/ }));
    fireEvent.change(screen.getByLabelText(/What should a reviewer check/), { target: { value: "Check it" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send to a reviewer" })));
    expect(screen.getByRole("alert")).toHaveTextContent(/no connection/);
    expect(screen.getByLabelText(/What should a reviewer check/)).toHaveValue("Check it");
  });
});

describe("video player (T29)", () => {
  it("shows the player when there is a playback URL, and reports load errors", () => {
    const onVideoError = vi.fn();
    const { container } = render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} videoUrl="https://s/v.mp4?sig" onVideoError={onVideoError} />);
    const video = container.querySelector("video")!;
    expect(video).toHaveAttribute("src", "https://s/v.mp4?sig");
    fireEvent.error(video);
    expect(onVideoError).toHaveBeenCalled();
    expect(screen.queryByText(/playback isn't available/)).not.toBeInTheDocument();
  });

  it("explains when there is no playable video", () => {
    render(<ResultView result={adaptResult(MOCK_MISINFO_PENDING)} videoUrl={null} />);
    expect(screen.getByText(/playback isn't available/)).toBeInTheDocument();
  });
});
