import { VERDICTS, type Verdict } from "@/lib/vocabulary";
import { Icon } from "./Icon";
import { TONE } from "./tone";

/** Evidence verdict: pill. Insufficient and unsupported have no fill and a dashed outline. */
export function VerdictChip({ verdict }: { verdict: Verdict }) {
  const m = VERDICTS[verdict];
  const unfilled = m.dashed ? "!bg-transparent border-dashed" : "";
  return (
    <span
      data-verdict={verdict}
      title={m.description}
      className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2 py-0.5 text-cap font-semibold ${TONE[m.tone]} ${unfilled}`}
    >
      <Icon name={m.icon} className="!h-3.5 !w-3.5" />
      {m.display}
    </span>
  );
}
