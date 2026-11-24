import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock("@/lib/supabase", () => ({
  getBrowserClient: () => ({ auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) } }),
}));

import { startAnalysis, uploadVideo, UploadError } from "./flow";

type Sent = { method: string; url: string; headers: Record<string, string>; body: unknown };
let sent: Sent[] = [];
let respond: (x: FakeXHR) => void = (x) => x.finish(200, "{}");

class FakeXHR {
  method = "";
  url = "";
  headers: Record<string, string> = {};
  status = 0;
  responseText = "";
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open(m: string, u: string) {
    this.method = m;
    this.url = u;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send(body: unknown) {
    sent.push({ method: this.method, url: this.url, headers: this.headers, body });
    queueMicrotask(() => respond(this));
  }
  abort() {
    this.onabort?.();
  }
  finish(status: number, text: string) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 5 });
    this.status = status;
    this.responseText = text;
    this.onload?.();
  }
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const file = new File([new Uint8Array(5)], "flu.mp4", { type: "video/mp4" });

beforeEach(() => {
  sent = [];
  apiFetch.mockReset();
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  respond = (x) => x.finish(200, "{}");
});
afterEach(() => vi.unstubAllGlobals());

describe("uploadVideo (T20 signed flow)", () => {
  it("asks for a signed URL, PUTs the file there, then registers it", async () => {
    apiFetch
      .mockResolvedValueOnce(json(201, { storage_key: "uploads/u/abc/flu.mp4", signed_url: "https://store.example/sign?token=t" }))
      .mockResolvedValueOnce(json(201, { video_id: "v1", duplicate: false }));
    const progress = vi.fn();
    const out = await uploadVideo(file, progress, new AbortController().signal);
    expect(out).toEqual({ videoId: "v1", duplicate: false });
    expect(apiFetch.mock.calls[0][0]).toBe("/v1/videos/uploads");
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ filename: "flu.mp4", size_bytes: 5, content_type: "video/mp4" });
    expect(sent[0]).toMatchObject({ method: "PUT", url: "https://store.example/sign?token=t" });
    expect(sent[0].body).toBeInstanceOf(FormData);
    expect(progress).toHaveBeenCalledWith(5, 5);
    expect(apiFetch.mock.calls[1][0]).toBe("/v1/videos");
    expect(JSON.parse(apiFetch.mock.calls[1][1].body)).toEqual({ storage_key: "uploads/u/abc/flu.mp4", filename: "flu.mp4" });
  });

  it("falls back to the legacy multipart upload when storage can't sign (501)", async () => {
    apiFetch.mockResolvedValueOnce(json(501, { detail: "signed uploads need STORAGE_BACKEND=supabase" }));
    respond = (x) => x.finish(200, JSON.stringify({ video_id: "v2" }));
    const out = await uploadVideo(file, vi.fn(), new AbortController().signal);
    expect(out.videoId).toBe("v2");
    expect(sent[0]).toMatchObject({ method: "POST", headers: { Authorization: "Bearer tok" } });
    expect(sent[0].url).toMatch(/\/videos\/upload$/);
  });

  it("turns the server's rejection into plain language", async () => {
    apiFetch.mockResolvedValueOnce(json(429, { detail: { code: "quota_exceeded", message: "x" } }));
    await expect(uploadVideo(file, vi.fn(), new AbortController().signal)).rejects.toThrow(/today's upload limit/);
  });

  it("rejects the registration of a stored file the server refuses", async () => {
    apiFetch
      .mockResolvedValueOnce(json(201, { storage_key: "k", signed_url: "https://s" }))
      .mockResolvedValueOnce(json(422, { detail: { code: "too_long", message: "200s > 180s" } }));
    await expect(uploadVideo(file, vi.fn(), new AbortController().signal)).rejects.toThrow("The video is longer than 3 minutes.");
  });

  it("reports a cancel as cancelled", async () => {
    apiFetch.mockResolvedValueOnce(json(201, { storage_key: "k", signed_url: "https://s" }));
    const ctrl = new AbortController();
    respond = () => ctrl.abort();
    const err = await uploadVideo(file, vi.fn(), ctrl.signal).catch((e) => e);
    expect(err).toBeInstanceOf(UploadError);
    expect(err.cancelled).toBe(true);
  });
});

describe("startAnalysis", () => {
  it("creates the job for the video", async () => {
    apiFetch.mockResolvedValueOnce(json(200, { job_id: "j1" }));
    expect(await startAnalysis("v1")).toBe("j1");
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ video_id: "v1" });
  });
});
