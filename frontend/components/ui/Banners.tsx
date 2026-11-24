import type { ReactNode } from "react";
import { Icon } from "./Icon";

// Pattern for every state: what happened · what it means for the result · one action.

type BannerProps = { title: string; children?: ReactNode; action?: ReactNode };

/** System failure (upload stopped, job failed). Never used for a verdict or label. */
export function ErrorBanner({ title, children, action }: BannerProps) {
  return (
    <div role="alert" className="flex gap-3 rounded-md border border-err-bd bg-err-bg p-4 text-err-fg">
      <Icon name="alert" className="mt-0.5" />
      <div className="flex flex-1 flex-col gap-1">
        <p className="text-h3">{title}</p>
        {children && <div className="text-small text-ink">{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}

/** Provisional result: waiting for a reviewer. Ochre, not red. */
export function ReviewBanner({ title = "Waiting for a reviewer. Treat this label as provisional.", children, action }: Partial<BannerProps>) {
  return (
    <div role="status" className="flex gap-3 rounded-md border border-warn-bd bg-warn-bg p-4 text-warn-fg">
      <Icon name="flag" className="mt-0.5" />
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-h3">{title}</p>
        {children && <div className="flex flex-wrap gap-2">{children}</div>}
        {action && <div>{action}</div>}
      </div>
    </div>
  );
}

/** Temporary problem (lost connection, retrying). */
export function WarnBanner({ title, children, action }: BannerProps) {
  return (
    <div role="status" className="flex items-start gap-3 rounded-md border border-warn-bd bg-warn-bg p-3 text-warn-fg">
      <Icon name="refresh" className="mt-0.5" />
      <div className="flex flex-1 flex-col gap-1">
        <p className="text-small font-semibold">{title}</p>
        {children && <div className="text-small text-ink">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({ icon = "inbox", title, children, action }: BannerProps & { icon?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface px-6 py-12 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-surface-sunken text-ink-2">
        <Icon name={icon} className="!h-6 !w-6" />
      </span>
      <p className="text-h2">{title}</p>
      {children && <div className="max-w-prose text-small text-ink-2">{children}</div>}
      {action}
    </div>
  );
}
