import { STANCES, type Stance } from "@/lib/vocabulary";
import { Icon } from "./Icon";

/** Speaker stance: square chip with no colour. Colour is reserved for judgements. */
export function StanceChip({ stance }: { stance: Stance }) {
  const m = STANCES[stance];
  return (
    <span
      data-stance={stance}
      title={m.description}
      className={`inline-flex w-fit items-center gap-1.5 rounded-sm border border-line-input bg-surface px-2 py-0.5 text-cap font-semibold ${
        m.dashed ? "border-dashed text-ink-2" : "text-ink"
      }`}
    >
      <Icon name={m.icon} className="!h-3.5 !w-3.5" />
      {m.display}
    </span>
  );
}
