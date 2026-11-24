// The upload, step by step (design §1 "Upload", T20):
//   1. POST /v1/videos/uploads   → a short-lived signed URL for one object
//   2. PUT the file to that URL  → straight to Supabase Storage, with progress
//   3. POST /v1/videos           → the API checks the stored file and registers it
//   4. POST /jobs/create         → the analysis starts
// When storage can't sign URLs (local development: 501), it falls back to the
// legacy multipart POST /videos/upload.

import { apiFetch } from "@/lib/api";
import { getBrowserClient } from "@/lib/supabase";
import { rejectionText } from "./rules";

export class UploadError extends Error {
  constructor(message: string, readonly cancelled = false) {
    super(message);
  }
}

type Progress = (sent: number, total: number) => void;

async function failed(res: Response): Promise<never> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* no body */
  }
  throw new UploadError(rejectionText(body, res.status));
}

/** XHR, because fetch can't report upload progress. */
function send(method: string, url: string, body: XMLHttpRequestBodyInit, onProgress: Progress, signal: AbortSignal, headers: Record<string, string> = {}) {
  return new Promise<{ status: number; text: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded, e.total);
    xhr.onload = () => resolve({ status: xhr.status, text: xhr.responseText });
    xhr.onerror = () => reject(new UploadError("The upload stopped: the connection was lost. Nothing was analysed."));
    xhr.onabort = () => reject(new UploadError("Upload cancelled. Nothing was analysed.", true));
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(body);
  });
}

const parse = (text: string): unknown => {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
};

/** Steps 1–3. Returns the registered video's id. */
export async function uploadVideo(file: File, onProgress: Progress, signal: AbortSignal): Promise<{ videoId: string; duplicate: boolean }> {
  const signedRes = await apiFetch("/v1/videos/uploads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, size_bytes: file.size, content_type: file.type || "video/mp4" }),
  });

  if (signedRes.status === 501) return legacyUpload(file, onProgress, signal);
  if (!signedRes.ok) await failed(signedRes);
  const signed = (await signedRes.json()) as { storage_key: string; signed_url: string };

  // Same body as supabase-js uploadToSignedUrl: multipart with the file in an unnamed field.
  const form = new FormData();
  form.append("cacheControl", "3600");
  form.append("", file);
  const put = await send("PUT", signed.signed_url, form, onProgress, signal, { "x-upsert": "false" });
  if (put.status < 200 || put.status >= 300) throw new UploadError("The upload stopped before it finished. Nothing was analysed.");

  const reg = await apiFetch("/v1/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ storage_key: signed.storage_key, filename: file.name }),
  });
  if (!reg.ok) await failed(reg);
  const video = (await reg.json()) as { video_id: string; duplicate?: boolean };
  return { videoId: video.video_id, duplicate: Boolean(video.duplicate) };
}

async function legacyUpload(file: File, onProgress: Progress, signal: AbortSignal) {
  const { data } = await getBrowserClient().auth.getSession();
  const form = new FormData();
  form.append("file", file);
  const res = await send("POST", `${process.env.NEXT_PUBLIC_API_URL}/videos/upload`, form, onProgress, signal, data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {});
  if (res.status < 200 || res.status >= 300) throw new UploadError(rejectionText(parse(res.text), res.status));
  const video = parse(res.text) as { video_id: string };
  return { videoId: video.video_id, duplicate: false };
}

/** Step 4. */
export async function startAnalysis(videoId: string): Promise<string> {
  const res = await apiFetch("/jobs/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
  });
  if (!res.ok) await failed(res);
  return ((await res.json()) as { job_id: string }).job_id;
}

/** Length from the browser's own reading of the file; null if it can't tell within 5 s. */
export function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    const t = setTimeout(() => done(null), 5000);
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      clearTimeout(t);
      done(Number.isFinite(v.duration) ? v.duration : null);
    };
    v.onerror = () => {
      clearTimeout(t);
      done(null);
    };
    v.src = url;
  });
}
