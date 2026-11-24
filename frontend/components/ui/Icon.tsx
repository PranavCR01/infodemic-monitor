import type { CSSProperties } from "react";

/** A stroke icon from public/icons, painted in the current text colour. Always decorative. */
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  const style = { "--m": `url(/icons/${name}.svg)` } as CSSProperties;
  return <span aria-hidden="true" data-icon={name} className={`icon ${className}`} style={style} />;
}
