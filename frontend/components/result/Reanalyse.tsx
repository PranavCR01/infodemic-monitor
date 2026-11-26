"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Button, Icon, buttonClass } from "@/components/ui";
import { REANALYSE_REASON_MAX, type ReanalyseOutcome } from "@/lib/api/reanalyse";

type Props = {
  onReanalyse: (reason: string) => Promise<ReanalyseOutcome>;
  /** Called with the new job's id once the server has accepted it. */
  onStarted: (jobId: string) => void;
};

/**
 * T55: "Re-analyse" on the result page, for the video's owner or an admin. A confirm
 * dialog names the cost (one more analysis) and takes an optional reason.
 */
export function Reanalyse({ onReanalyse, onStarted }: Props) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function start() {
    setError(null);
    setSending(true);
    const r = await onReanalyse(reason);
    setSending(false);
    if (r.ok) {
      setOpen(false);
      onStarted(r.jobId);
    } else setError(r.message);
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setError(null);
      }}
    >
      <Dialog.Trigger className={buttonClass("secondary", "sm")}>
        <Icon name="refresh" className="!h-3.5 !w-3.5" /> Re-analyse
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex w-[calc(100vw-2rem)] max-w-[480px] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-lg border border-line bg-surface p-5 shadow-3">
          <Dialog.Title className="text-h2 text-ink">Re-analyse this video?</Dialog.Title>
          <Dialog.Description className="text-small text-ink-2">
            This runs <strong className="text-ink">one more analysis</strong> of the video with the current system. The result you see now
            stays available under &ldquo;Previous analyses&rdquo;. A video can be re-analysed a few times a day.
          </Dialog.Description>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ra-reason" className="text-small font-semibold text-ink">
              Reason <span className="font-normal text-ink-3">(optional)</span>
            </label>
            <textarea
              id="ra-reason"
              rows={3}
              maxLength={REANALYSE_REASON_MAX}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="For example: the search has been improved since this result."
              aria-describedby={error ? "ra-error" : undefined}
              className="w-full rounded-md border border-line-input bg-surface px-3 py-2 text-body text-ink"
            />
          </div>
          {error && (
            <p id="ra-error" role="alert" className="rounded-md border border-err-bd bg-err-bg px-3 py-2 text-small text-err-fg">
              {error}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Dialog.Close className={buttonClass("ghost", "sm")}>Cancel</Dialog.Close>
            <Button size="sm" onClick={start} disabled={sending}>
              {sending ? "Starting…" : "Start re-analysis"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
