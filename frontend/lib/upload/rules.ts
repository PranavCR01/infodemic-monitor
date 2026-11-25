// Upload rules (HANDOFF §6.2; lead decision Q4: 3-minute limit, backend #77).
// Checked in the browser before uploading, so nobody waits for a file the server
// will refuse. The server checks again (T20 guardrails); these are not the control.

export const MAX_BYTES = 100 * 1024 * 1024; // config/guardrails.yaml max_file_bytes
export const MAX_SECONDS = 180;
export const ACCEPT = "video/mp4,video/quicktime,.mp4,.mov";

const EXT = /\.(mp4|mov)$/i;
const TYPES = ["video/mp4", "video/quicktime"];

export type FileProblem = { title: string; detail: string };

const mb = (bytes: number) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

export function duration(seconds: number): string {
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  if (m && s % 60 === 0) return `${m} minute${m === 1 ? "" : "s"}`;
  return m ? `${m} min ${s % 60} s` : `${s} s`;
}

/** Type and size, from the File alone. */
export function checkFile(f: { name: string; size: number; type: string }, maxBytes = MAX_BYTES): FileProblem | null {
  if (!TYPES.includes(f.type) && !EXT.test(f.name)) {
    return { title: "This file type can't be analysed", detail: `${f.name} isn't an MP4 or MOV video. Choose an MP4 or MOV file.` };
  }
  if (f.size === 0) return { title: "This file is empty", detail: `${f.name} has no content. Choose another file.` };
  if (f.size > maxBytes) {
    return { title: "This video is too large to analyse", detail: `${f.name} is ${mb(f.size)}. The limit is ${mb(maxBytes).replace(".0", "")}. Trim or compress it and upload again.` };
  }
  return null;
}

/** Length, once the browser has read the video's metadata. Unknown length passes: the server checks it. */
export function checkDuration(name: string, seconds: number | null, maxSeconds = MAX_SECONDS): FileProblem | null {
  if (seconds === null || !Number.isFinite(seconds)) return null;
  if (seconds > maxSeconds) {
    return { title: "This video is too long to analyse", detail: `${name} is ${duration(seconds)}. The limit is ${duration(maxSeconds)}. Trim it and upload again.` };
  }
  return null;
}

/** Server rejections (T20 rejection_to_http: {detail: {code, message}}) in plain language. */
const REJECTIONS: Record<string, string> = {
  file_too_large: "The video is larger than the limit.",
  too_long: "The video is longer than 3 minutes.",
  too_short: "The video is too short to analyse.",
  empty_file: "The file is empty.",
  unsupported_media: "This isn't a video format we can analyse. Use MP4 or MOV.",
  media_mismatch: "The file's contents don't match its type. It may be damaged or renamed.",
  corrupt_media: "The video file looks damaged and can't be read.",
  quota_exceeded: "You've reached today's upload limit. Try again tomorrow, or ask your project lead.",
  rate_limited: "Too many uploads in a short time. Wait a minute, then try again.",
};

export function rejectionText(body: unknown, status: number): string {
  const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
  if (code && REJECTIONS[code]) return REJECTIONS[code];
  if (status === 401) return "Your session ended. Sign in again, then upload.";
  if (status === 413) return REJECTIONS.file_too_large;
  if (status >= 500) return "The upload service isn't available right now. Try again in a moment.";
  return "The upload wasn't accepted. Try again, or choose another file.";
}

/** "About 8 seconds left" from bytes sent so far. */
export function timeLeft(sent: number, total: number, elapsedMs: number): string {
  if (sent <= 0 || elapsedMs < 500) return "";
  const rate = sent / elapsedMs; // bytes per ms
  const s = Math.max(1, Math.round((total - sent) / rate / 1000));
  return s < 60 ? `About ${s} second${s === 1 ? "" : "s"} left` : `About ${Math.round(s / 60)} min left`;
}

export const progressText = (sent: number, total: number) => `${(sent / 1048576).toFixed(1)} of ${(total / 1048576).toFixed(1)} MB`;
