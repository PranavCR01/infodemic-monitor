import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const flush = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

describe("usePolling", () => {
  it("keeps polling after successful polls (doesn't stop after the first)", async () => {
    const poll = vi.fn().mockResolvedValue(true);
    renderHook(() => usePolling(poll, false));
    await flush(3000);
    await flush(3000);
    await flush(3000);
    expect(poll).toHaveBeenCalledTimes(3);
  });

  it("stops when done", async () => {
    const poll = vi.fn().mockResolvedValue(true);
    const { rerender } = renderHook(({ done }) => usePolling(poll, done), { initialProps: { done: false } });
    await flush(3000);
    rerender({ done: true });
    await flush(30_000);
    expect(poll).toHaveBeenCalledTimes(1);
  });

  it("reports a lost connection after 3 failures in a row, and recovers", async () => {
    let ok = false;
    const poll = vi.fn(async () => ok);
    const { result } = renderHook(() => usePolling(poll, false));
    await flush(3000);
    await flush(3000);
    expect(result.current.lost).toBe(false);
    await flush(3000);
    expect(result.current.lost).toBe(true);
    ok = true;
    await act(async () => {
      await result.current.checkNow();
    });
    expect(result.current.lost).toBe(false);
  });

  it("skips polls while the tab is hidden", async () => {
    const poll = vi.fn().mockResolvedValue(true);
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    renderHook(() => usePolling(poll, false));
    await flush(9000);
    expect(poll).not.toHaveBeenCalled();
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(poll).toHaveBeenCalledTimes(1);
  });
});
