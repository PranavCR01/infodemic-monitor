"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);

    try {
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await apiFetch("/videos/upload", { method: "POST", body: form });
      if (!uploadRes.ok) {
        const body = await uploadRes.json().catch(() => ({}));
        throw new Error(body.detail ?? "Upload failed");
      }
      const { video_id } = await uploadRes.json();

      const jobRes = await apiFetch("/jobs/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id }),
      });
      if (!jobRes.ok) {
        const body = await jobRes.json().catch(() => ({}));
        throw new Error(body.detail ?? "Job creation failed");
      }
      const { job_id } = await jobRes.json();
      setJobId(job_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <PageHeader />
      <main className="flex-1 flex items-center justify-center p-6">
        {jobId ? (
          <SuccessCard
            jobId={jobId}
            onReset={() => { setFile(null); setJobId(null); }}
          />
        ) : (
          <UploadCard
            file={file}
            setFile={setFile}
            inputRef={inputRef}
            uploading={uploading}
            error={error}
            onUpload={handleUpload}
          />
        )}
      </main>
    </div>
  );
}

function PageHeader() {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="max-w-5xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-[#009edb] flex items-center justify-center">
            <span className="text-white font-bold text-xs">WHO</span>
          </div>
          <span className="font-semibold text-gray-900 text-sm">Infodemic Monitor</span>
        </div>
        <nav className="text-sm">
          <Link href="/jobs" className="text-gray-500 hover:text-gray-900 transition-colors">
            Job History
          </Link>
        </nav>
      </div>
    </header>
  );
}

function SuccessCard({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  return (
    <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full text-center">
      <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
        <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-gray-900 mb-2">Analysis started</h2>
      <p className="text-sm text-gray-500 mb-6">Your video is being processed. This may take a minute.</p>
      <div className="flex gap-3 justify-center">
        <Link
          href={`/jobs/${jobId}`}
          className="px-4 py-2 bg-[#009edb] hover:bg-[#0081b3] text-white text-sm font-medium rounded-lg transition-colors"
        >
          Track progress →
        </Link>
        <button
          onClick={onReset}
          className="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
        >
          Analyze another
        </button>
      </div>
    </div>
  );
}

function UploadCard({
  file,
  setFile,
  inputRef,
  uploading,
  error,
  onUpload,
}: {
  file: File | null;
  setFile: (f: File | null) => void;
  inputRef: React.RefObject<HTMLInputElement>;
  uploading: boolean;
  error: string | null;
  onUpload: () => void;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
      <h2 className="text-base font-semibold text-gray-900 mb-1">Analyze a video</h2>
      <p className="text-sm text-gray-500 mb-6">
        Upload a short-form video to detect health misinformation.
      </p>

      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const dropped = e.dataTransfer.files[0];
          if (dropped) setFile(dropped);
        }}
        className="border-2 border-dashed border-gray-300 hover:border-[#009edb] rounded-xl p-8 text-center cursor-pointer transition-colors"
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <div>
            <p className="text-sm font-medium text-gray-900 truncate max-w-xs mx-auto">{file.name}</p>
            <p className="text-xs text-gray-400 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
          </div>
        ) : (
          <div>
            <svg
              className="w-8 h-8 text-gray-400 mx-auto mb-2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-sm text-gray-500">
              Drop a video here or <span className="text-[#009edb]">browse</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">MP4, MOV, WebM</p>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <button
        onClick={onUpload}
        disabled={!file || uploading}
        className="mt-4 w-full py-2 px-4 bg-[#009edb] hover:bg-[#0081b3] disabled:opacity-50 text-white font-medium rounded-lg text-sm transition-colors"
      >
        {uploading ? "Uploading…" : "Analyze"}
      </button>
    </div>
  );
}
