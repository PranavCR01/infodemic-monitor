import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { fetchPlayback, refreshDelay, usePlaybackUrl } from "./playback";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

beforeEach(() => apiFetch.mockReset());
afterEach(() => vi.useRealTimers());

describe("fetchPlayback (T29)", () => {
  it("reads the signed URL and its expiry, without caching", async () => {
    apiFetch.mockResolvedValueOnce(json(200, { url: "https://s/v.mp4?sig", expires_at: "2026-11-24T02:10:00Z", expires_in_seconds: 600 }));
    expect(await fetchPlayback("j1")).toEqual({ url: "https://s/v.mp4?sig", expiresAt: Date.parse("2026-11-24T02:10:00Z") });
    expect(apiFetch).toHaveBeenCalledWith("/v1/jobs/j1/playback", { cache: "no-store" });
  });

  // 404 also covers an analyst asking for someone else's job: T33's ownership rule answers
  // a hidden job exactly like a missing one (backend test_ownership_t33 covers the route).
  it.each([404, 501, 503])("gives no player on %s", async (status) => {
    apiFetch.mockResolvedValueOnce(json(status, { detail: "x" }));
    expect(await fetchPlayback("j1")).toBeNull();
  });

  it("gives no player on a malformed answer or no connection", async () => {
    apiFetch.mockResolvedValueOnce(json(200, { url: "" }));
    expect(await fetchPlayback("j1")).toBeNull();
    apiFetch.mockRejectedValueOnce(new TypeError("offline"));
    expect(await fetchPlayback("j1")).toBeNull();
  });
});

describe("refreshDelay", () => {
  it("renews a minute before expiry, never sooner than 5 s from now", () => {
    expect(refreshDelay(600_000, 0)).toBe(540_000);
    expect(refreshDelay(30_000, 0)).toBe(5_000);
  });
});

describe("usePlaybackUrl", () => {
  it("renews the URL before it expires", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse("2026-11-24T02:00:00Z"));
    apiFetch
      .mockResolvedValueOnce(json(200, { url: "u1", expires_at: "2026-11-24T02:10:00Z" }))
      .mockResolvedValueOnce(json(200, { url: "u2", expires_at: "2026-11-24T02:20:00Z" }));
    const { result } = renderHook(() => usePlaybackUrl("j1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.url).toBe("u1");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9 * 60_000);
    });
    expect(result.current.url).toBe("u2");
  });

  it("fetches a fresh URL once when the player fails, not in a loop", async () => {
    apiFetch.mockResolvedValue(json(200, { url: "u", expires_at: new Date(Date.now() + 600_000).toISOString() }));
    const { result } = renderHook(() => usePlaybackUrl("j1"));
    await act(async () => {});
    await act(async () => {
      result.current.onError();
      result.current.onError();
    });
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("asks for nothing until there is a result", () => {
    renderHook(() => usePlaybackUrl(null));
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
