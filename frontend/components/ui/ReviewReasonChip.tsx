import { reasonText } from "@/lib/vocabulary";
import { Icon } from "./Icon";

/**
 * Why a case needs review, in plain language. Pass `text` when the API supplies it
 * (T26); otherwise the code is looked up in the vocabulary. The code itself is never shown.
 */
export function ReviewReasonChip({ code, text }: { code: string; text?: string | null }) {
  return (
    <span className="inline-flex w-fit items-start gap-1.5 rounded-sm border border-warn-bd bg-warn-bg px-2 py-1 text-small text-warn-fg">
      <Icon name="flag" className="mt-0.5 !h-3.5 !w-3.5" />
      {text || reasonText(code)}
    </span>
  );
}
