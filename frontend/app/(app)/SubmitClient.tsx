"use client";

import { useRouter } from "next/navigation";
import { SubmitVideo } from "@/components/upload/SubmitVideo";
import { readDuration, startAnalysis, uploadVideo } from "@/lib/upload/flow";

export function SubmitClient() {
  const router = useRouter();
  return <SubmitVideo deps={{ readDuration, uploadVideo, startAnalysis, goToJob: (id) => router.push(`/jobs/${id}`) }} />;
}
