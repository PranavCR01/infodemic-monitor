"use client";

import { SubmitVideo } from "@/components/upload/SubmitVideo";
import { readDuration, UploadError } from "@/lib/upload/flow";

/** MOCK upload: the file never leaves the browser. Uses the browser's real duration check. */
export default function UploadPreview() {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <p role="note" className="mb-4 rounded-md border border-warn-bd bg-warn-bg px-3 py-2 text-small text-warn-fg">
        <strong>Mock upload.</strong> Nothing is sent anywhere.
      </p>
      <SubmitVideo
        deps={{
          readDuration,
          uploadVideo: (f, onProgress, signal) =>
            new Promise((resolve, reject) => {
              let sent = 0;
              const t = setInterval(() => {
                sent = Math.min(f.size, sent + f.size / 20);
                onProgress(sent, f.size);
                if (sent >= f.size) {
                  clearInterval(t);
                  resolve({ videoId: "mock", duplicate: false });
                }
              }, 150);
              signal.addEventListener("abort", () => {
                clearInterval(t);
                reject(new UploadError("Upload cancelled.", true));
              });
            }),
          startAnalysis: async () => "mock-job",
          goToJob: () => alert("Would open the progress page."),
        }}
      />
    </div>
  );
}
