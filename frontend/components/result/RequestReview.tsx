"use client";

import { useState } from "react";
import { Button, Icon } from "@/components/ui";
import { REQUEST_NOTE_MAX, requestNoteProblem, type RequestOutcome } from "@/lib/api/review-request";

/**
 * "Request review" (T32) on a result the review rule didn't send to review.
 * A note is required, so the reviewer knows where to look.
 */
export function RequestReview({ onRequest }: { onRequest: (note: string) => Promise<RequestOutcome> }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <p role="status" className="flex items-center gap-1.5 text-small text-ink">
        <Icon name="flag" className="!h-3.5 !w-3.5 text-warn-fg" />
        Review requested. Treat the label as provisional until a reviewer has checked it.
      </p>
    );
  }
  if (!open) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)} aria-expanded="false">
        <Icon name="flag" className="!h-3.5 !w-3.5" /> Request review
      </Button>
    );
  }
  return (
    <form
      className="flex w-full flex-col gap-2 rounded-md border border-line bg-surface-2 p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const problem = requestNoteProblem(note);
        setError(problem);
        if (problem) return;
        setSending(true);
        const r = await onRequest(note);
        setSending(false);
        if (r.ok) setDone(true);
        else setError(r.message);
      }}
    >
      <label htmlFor="rr-note" className="text-small font-semibold text-ink">
        What should a reviewer check? <span aria-hidden="true">*</span>
      </label>
      <textarea
        id="rr-note"
        rows={3}
        maxLength={REQUEST_NOTE_MAX}
        value={note}
        autoFocus
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "rr-error" : undefined}
        onChange={(e) => setNote(e.target.value)}
        className={`w-full rounded-md border bg-surface px-3 py-2 text-body text-ink ${error ? "border-err-fg" : "border-line-input"}`}
      />
      {error && (
        <p id="rr-error" role="alert" className="text-small text-err-fg">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={sending}>
          {sending ? "Sending…" : "Send to a reviewer"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => { setOpen(false); setError(null); }}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
