"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

type Job = {
  job_id: string;
  status: "PENDING" | "STARTED" | "SUCCESS" | "FAILED";
  error_code: string | null;
  created_at: string;
  filename: string;
  label: string | null;
  confidence: number | null;
};

function relativeTime(isoString: string): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function StatusBadge({ status, error_code }: { status: Job["status"]; error_code: string | null }) {
  if (status === "PENDING") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
        Pending
      </span>
    );
  }
  if (status === "STARTED") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
        Processing
      </span>
    );
  }
  if (status === "SUCCESS") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
        Complete
      </span>
    );
  }
  return (
    <span
      title={error_code ?? undefined}
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 cursor-help"
    >
      Failed
    </span>
  );
}

const LABEL_STYLES: Record<string, string> = {
  MISINFO: "bg-red-100 text-red-700",
  NO_MISINFO: "bg-green-100 text-green-700",
  DEBUNKING: "bg-blue-100 text-blue-700",
  CANNOT_RECOGNIZE: "bg-gray-100 text-gray-600",
};

const LABEL_DISPLAY: Record<string, string> = {
  MISINFO: "Misinfo",
  NO_MISINFO: "No Misinfo",
  DEBUNKING: "Debunking",
  CANNOT_RECOGNIZE: "Unclear",
};

function LabelBadge({ label, confidence }: { label: string; confidence: number | null }) {
  const style = LABEL_STYLES[label] ?? "bg-gray-100 text-gray-600";
  const display = LABEL_DISPLAY[label] ?? label;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {display}
      {confidence !== null && (
        <span className="opacity-70">{Math.round(confidence * 100)}%</span>
      )}
    </span>
  );
}

export function JobsView({ initialJobs }: { initialJobs: Job[] }) {
  const [jobs, setJobs] = useState<Job[]>(initialJobs);

  useEffect(() => {
    const hasActive = jobs.some(
      (j) => j.status === "PENDING" || j.status === "STARTED"
    );
    if (!hasActive) return;

    const interval = setInterval(async () => {
      try {
        const res = await apiFetch("/jobs?limit=50");
        if (res.ok) setJobs(await res.json());
      } catch {
        // ignore transient errors
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [jobs]);

  if (jobs.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500 mb-4">No analyses yet.</p>
        <Link href="/" className="text-[#009edb] hover:underline text-sm">
          Upload a video to get started →
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="text-left px-4 py-3 font-medium text-gray-600">Video</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Label</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Submitted</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 text-gray-900">
                <span className="truncate block max-w-[200px]" title={job.filename}>
                  {job.filename.length > 40
                    ? job.filename.slice(0, 37) + "…"
                    : job.filename}
                </span>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={job.status} error_code={job.error_code} />
              </td>
              <td className="px-4 py-3">
                {job.status === "SUCCESS" && job.label ? (
                  <LabelBadge label={job.label} confidence={job.confidence} />
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                {job.created_at ? relativeTime(job.created_at) : "—"}
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/jobs/${job.job_id}`}
                  className="text-[#009edb] hover:text-[#0081b3] font-medium"
                >
                  View →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
