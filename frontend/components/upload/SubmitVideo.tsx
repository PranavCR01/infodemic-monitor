"use client";

import { useRef, useState, type DragEvent } from "react";
import { Button, ErrorBanner, Icon } from "@/components/ui";
import { ACCEPT, checkDuration, checkFile, duration, MAX_SECONDS, progressText, timeLeft, type FileProblem } from "@/lib/upload/rules";
import { UploadError } from "@/lib/upload/flow";

export type UploadDeps = {
  readDuration: (f: File) => Promise<number | null>;
  uploadVideo: (f: File, onProgress: (sent: number, total: number) => void, signal: AbortSignal) => Promise<{ videoId: string; duplicate: boolean }>;
  startAnalysis: (videoId: string) => Promise<string>;
  goToJob: (jobId: string) => void;
};

type State =
  | { kind: "idle" }
  | { kind: "checking"; file: File }
  | { kind: "uploading"; file: File; seconds: number | null; sent: number; total: number; startedAt: number }
  | { kind: "ready"; file: File; seconds: number | null; videoId: string; duplicate: boolean }
  | { kind: "starting"; file: File; seconds: number | null }
  | { kind: "error"; problem: FileProblem; afterUpload: boolean };

const mb = (b: number) => `${(b / 1048576).toFixed(1)} MB`;

/** Submit.dc.html. "Paste a link" is shown but disabled ("Coming soon"). */
export function SubmitVideo({ deps }: { deps: UploadDeps }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function pick(file: File | undefined) {
    if (!file) return;
    const typeProblem = checkFile(file);
    if (typeProblem) return setState({ kind: "error", problem: typeProblem, afterUpload: false });
    setState({ kind: "checking", file });
    const seconds = await deps.readDuration(file);
    const lengthProblem = checkDuration(file.name, seconds);
    if (lengthProblem) return setState({ kind: "error", problem: lengthProblem, afterUpload: false });

    abort.current = new AbortController();
    setState({ kind: "uploading", file, seconds, sent: 0, total: file.size, startedAt: Date.now() });
    try {
      const { videoId, duplicate } = await deps.uploadVideo(
        file,
        (sent, total) => setState((s) => (s.kind === "uploading" ? { ...s, sent, total } : s)),
        abort.current.signal,
      );
      setState({ kind: "ready", file, seconds, videoId, duplicate });
    } catch (e) {
      const err = e instanceof UploadError ? e : new UploadError("The upload stopped. Nothing was analysed.");
      if (err.cancelled) return setState({ kind: "idle" });
      setState({ kind: "error", problem: { title: "The upload stopped", detail: err.message }, afterUpload: true });
    }
  }

  async function start() {
    if (state.kind !== "ready") return;
    const { file, seconds, videoId } = state;
    setState({ kind: "starting", file, seconds });
    try {
      deps.goToJob(await deps.startAnalysis(videoId));
    } catch (e) {
      setState({ kind: "error", problem: { title: "The analysis couldn't be started", detail: e instanceof Error ? e.message : "Try again." }, afterUpload: true });
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void pick(e.dataTransfer.files?.[0]);
  };
  const busy = state.kind === "checking" || state.kind === "uploading" || state.kind === "starting";
  const file = "file" in state ? state.file : null;
  const seconds = "seconds" in state ? state.seconds : null;

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section aria-labelledby="submit-h" className="flex flex-col gap-4">
        <h1 id="submit-h" className="font-serif text-h1 text-ink">Submit a video</h1>
        <div role="tablist" aria-label="How to add a video" className="flex gap-1 border-b border-line">
          <span role="tab" aria-selected="true" className="border-b-2 border-primary px-3 py-2 text-small font-semibold text-ink">Upload a file</span>
          <span role="tab" aria-selected="false" aria-disabled="true" className="flex items-center gap-2 px-3 py-2 text-small text-ink-3">
            Paste a link <span className="rounded-sm border border-line px-1.5 text-cap">Coming soon</span>
          </span>
        </div>

        {(state.kind === "idle" || state.kind === "error") && (
          <label
            htmlFor="file"
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex cursor-pointer flex-col items-center gap-3 rounded-lg border-2 border-dashed bg-surface px-6 py-14 text-center ${dragging ? "border-primary bg-primary-subtle" : "border-line-input"}`}
          >
            <span className="grid h-14 w-14 place-items-center rounded-full bg-primary-subtle text-primary">
              <Icon name="upload" className="!h-7 !w-7" />
            </span>
            <span className="text-h2 text-ink">
              Drag a video here, or <span className="text-primary underline">choose a file</span>
            </span>
            <span className="text-small text-ink-2">MP4 or MOV · up to 100 MB · up to {duration(MAX_SECONDS)}</span>
            <input
              ref={input}
              id="file"
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                void pick(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
        )}

        {state.kind === "error" && (
          <ErrorBanner title={state.problem.title} action={<Button variant="secondary" size="sm" onClick={() => input.current?.click()}>Choose another file</Button>}>
            {state.problem.detail}
            {state.afterUpload ? "" : " Nothing was uploaded."}
          </ErrorBanner>
        )}

        {file && state.kind !== "error" && (
          <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-1">
            <div className="flex flex-wrap items-center gap-3">
              <Icon name="file" className="text-ink-2" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-small text-ink">{file.name}</p>
                <p className="text-cap text-ink-3">
                  {mb(file.size)}
                  {seconds !== null ? ` · ${duration(seconds)}` : ""}
                </p>
              </div>
              {state.kind === "uploading" && (
                <Button variant="secondary" size="sm" onClick={() => abort.current?.abort()}>Cancel</Button>
              )}
            </div>
            {state.kind === "checking" && <p className="text-small text-ink-2" aria-live="polite">Checking the video…</p>}
            {state.kind === "uploading" && (
              <>
                <div role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((state.sent / state.total) * 100)} className="h-2 overflow-hidden rounded-full bg-surface-sunken">
                  <span className="block h-full bg-primary" style={{ width: `${(state.sent / state.total) * 100}%` }} />
                </div>
                <p className="flex justify-between text-cap text-ink-2">
                  <span>Uploading… {progressText(state.sent, state.total)}</span>
                  <span>{timeLeft(state.sent, state.total, Date.now() - state.startedAt)}</span>
                </p>
              </>
            )}
            {state.kind === "ready" && (
              <p role="status" className="flex items-center gap-1.5 text-small text-ink">
                <Icon name="checkc" className="!h-4 !w-4 text-nomisinfo-fg" />
                Uploaded{state.duplicate ? ". This video was submitted before; its earlier analysis may be reused." : "."}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2">
          <Button onClick={start} disabled={state.kind !== "ready"} className="w-fit">
            {state.kind === "starting" ? "Starting…" : "Start analysis"}
          </Button>
          <p className="text-small text-ink-2">You&apos;ll go to the progress page. You can leave it; the result is saved to your videos.</p>
        </div>
        {busy && <p className="sr-only" aria-live="polite">{state.kind === "uploading" ? "Uploading" : "Working"}</p>}
      </section>

      <aside className="flex flex-col gap-3 rounded-lg border border-line bg-surface-2 p-5 text-small text-ink-2">
        <h2 className="text-h3 text-ink">What gets checked</h2>
        <ul className="flex list-disc flex-col gap-1.5 pl-5">
          <li>Spoken words and on-screen text</li>
          <li>Each health claim, with timestamps</li>
          <li>Whether the speaker endorses, refutes or quotes it</li>
          <li>PubMed research and official sources (WHO, CDC, FDA…)</li>
        </ul>
        <p>Uncertain or high-risk results go to a human reviewer before they are final.</p>
      </aside>
    </div>
  );
}
