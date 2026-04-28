"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { apiFetch } from "../../../lib/api";
import { SignOutButton } from "../../components/SignOutButton";

type JobStatus = "PENDING" | "STARTED" | "SUCCESS" | "FAILED";

type Job = {
  job_id: string;
  status: JobStatus;
  error_code: string | null;
  created_at: string;
};

type Citation = {
  claim: string;
  title: string;
  pmid: string;
  url: string;
};

type Result = {
  job_id: string;
  filename: string | null;
  label: string;
  confidence: number;
  explanation: string;
  evidence_snippets: string[];
  citations: Citation[] | null;
  provider: string;
  model_used: string;
  latency_ms: number;
  submitted_at: string;
};

const LABEL_STYLES: Record<string, string> = {
  MISINFO: "bg-red-100 text-red-700",
  NO_MISINFO: "bg-green-100 text-green-700",
  DEBUNKING: "bg-blue-100 text-blue-700",
  CANNOT_RECOGNIZE: "bg-gray-100 text-gray-600",
};

const LABEL_DISPLAY: Record<string, string> = {
  MISINFO: "Misinformation",
  NO_MISINFO: "No Misinformation",
  DEBUNKING: "Debunking",
  CANNOT_RECOGNIZE: "Cannot Recognize",
};

const ERROR_MESSAGES: Record<string, string> = {
  STORAGE_ERROR: "Could not retrieve the video file.",
  TRANSCRIPTION_ERROR: "Audio transcription failed.",
  INFERENCE_ERROR: "AI classification failed.",
  GROUNDING_ERROR: "PubMed grounding failed.",
  UNKNOWN_ERROR: "An unexpected error occurred.",
};

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function JobDetailClient({
  jobId,
  initialJob,
  initialResult,
}: {
  jobId: string;
  initialJob: Job;
  initialResult: Result | null;
}) {
  const [job, setJob] = useState<Job>(initialJob);
  const [result, setResult] = useState<Result | null>(initialResult);

  const isActive = job.status === "PENDING" || job.status === "STARTED";

  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(async () => {
      try {
        const jobRes = await apiFetch(`/jobs/${jobId}`);
        if (!jobRes.ok) return;
        const updatedJob: Job = await jobRes.json();
        setJob(updatedJob);

        if (updatedJob.status === "SUCCESS") {
          const resultRes = await apiFetch(`/jobs/${jobId}/result`);
          if (resultRes.ok) setResult(await resultRes.json());
        }
      } catch {
        // ignore transient errors
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [isActive, jobId]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-[#009edb] flex items-center justify-center">
              <span className="text-white font-bold text-xs">WHO</span>
            </div>
            <span className="font-semibold text-gray-900 text-sm">Infodemic Monitor</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/jobs" className="text-gray-500 hover:text-gray-900 transition-colors">
              ← Job History
            </Link>
            <SignOutButton />
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-8">
        {isActive && <InProgressView />}
        {job.status === "FAILED" && <FailedView job={job} />}
        {job.status === "SUCCESS" && result && <ResultView result={result} />}
      </main>
    </div>
  );
}

function InProgressView() {
  return (
    <div className="text-center py-16">
      <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center mx-auto mb-4">
        <span className="w-5 h-5 rounded-full bg-blue-500 animate-pulse block" />
      </div>
      <h2 className="text-lg font-semibold text-gray-900 mb-2">Analysis in progress…</h2>
      <p className="text-sm text-gray-500">Checking for updates every 5 seconds.</p>
    </div>
  );
}

function FailedView({ job }: { job: Job }) {
  const message =
    job.error_code ? (ERROR_MESSAGES[job.error_code] ?? ERROR_MESSAGES.UNKNOWN_ERROR) : ERROR_MESSAGES.UNKNOWN_ERROR;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-red-100 p-8">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
          <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Analysis failed</h2>
          {job.error_code && (
            <p className="text-xs text-gray-400 font-mono">{job.error_code}</p>
          )}
        </div>
      </div>
      <p className="text-sm text-gray-600">{message}</p>
    </div>
  );
}

function ResultView({ result }: { result: Result }) {
  const labelStyle = LABEL_STYLES[result.label] ?? "bg-gray-100 text-gray-600";
  const labelDisplay = LABEL_DISPLAY[result.label] ?? result.label;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-400 mb-1 font-mono truncate max-w-xs" title={result.filename ?? undefined}>
              {result.filename ?? "Unknown file"}
            </p>
            <div className="flex items-center gap-3">
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${labelStyle}`}>
                {labelDisplay}
              </span>
              <span className="text-2xl font-bold text-gray-900">
                {Math.round(result.confidence * 100)}%
              </span>
              <span className="text-sm text-gray-400">confidence</span>
            </div>
          </div>
        </div>
      </div>

      {/* Explanation */}
      <Section title="Explanation">
        <p className="text-sm text-gray-700 leading-relaxed">{result.explanation}</p>
      </Section>

      {/* Evidence snippets */}
      {result.evidence_snippets.length > 0 && (
        <Section title="Evidence Snippets">
          <div className="space-y-3">
            {result.evidence_snippets.map((snippet, i) => (
              <blockquote
                key={i}
                className="border-l-4 border-[#009edb] pl-4 py-1 text-sm text-gray-700 italic bg-blue-50 rounded-r-lg"
              >
                {snippet}
              </blockquote>
            ))}
          </div>
        </Section>
      )}

      {/* PubMed citations */}
      {result.citations && result.citations.length > 0 && (
        <Section title="PubMed Citations">
          <div className="space-y-3">
            {result.citations.map((c, i) => (
              <div key={i} className="border border-gray-200 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-2">
                  Claim: <span className="italic">{c.claim}</span>
                </p>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-[#009edb] hover:text-[#0081b3] hover:underline"
                >
                  {c.title} ↗
                </a>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Metadata */}
      <Section title="Metadata">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <MetaItem label="Provider" value={result.provider} />
          <MetaItem label="Model" value={result.model_used} />
          <MetaItem label="Latency" value={`${result.latency_ms.toLocaleString()} ms`} />
          <MetaItem label="Submitted" value={formatDate(result.submitted_at)} />
        </dl>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
      {children}
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-gray-400 text-xs uppercase tracking-wide">{label}</dt>
      <dd className="text-gray-700 font-medium mt-0.5 truncate">{value}</dd>
    </div>
  );
}
