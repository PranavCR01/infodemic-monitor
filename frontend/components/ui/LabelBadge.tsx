import { LABELS, labelDisplay, type MisinfoBasis, type VideoLabel } from "@/lib/vocabulary";
import { Icon } from "./Icon";
import { TONE } from "./tone";

type Props = { label: VideoLabel; basis?: MisinfoBasis | null; size?: "sm" | "lg"; showDescription?: boolean };

/** Video label: square-ish badge, tinted, icon + display name. CANNOT RECOGNIZE is dashed. */
export function LabelBadge({ label, basis, size = "sm", showDescription = false }: Props) {
  const m = LABELS[label];
  const { display, description } = labelDisplay(label, basis);
  return (
    <span className="inline-flex flex-col gap-1">
      <span
        data-label={label}
        title={description}
        className={`inline-flex w-fit items-center gap-1.5 rounded-sm border font-bold tracking-wide ${
          size === "lg" ? "px-3 py-2 text-xl" : "px-2 py-0.5 text-cap"
        } ${TONE[m.tone]} ${m.dashed ? "border-dashed" : ""}`}
      >
        <Icon name={m.icon} className={size === "lg" ? "!h-6 !w-6" : ""} />
        {display}
      </span>
      {showDescription && <span className="text-small text-ink-2">{description}</span>}
    </span>
  );
}
