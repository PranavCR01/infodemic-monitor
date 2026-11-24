// WCAG 2.x relative luminance and contrast ratio. Used by the token check
// (scripts/check-contrast.ts via vitest) so a token change can't silently drop below AA.

export function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `--name: #hex` pairs from one CSS block. */
export function parseTokens(css: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of Array.from(css.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})\b/g))) out[m[1]] = m[2];
  return out;
}

/** Light tokens (`:root`) and dark tokens (light overridden by `[data-theme="dark"]`). */
export function themes(css: string): { light: Record<string, string>; dark: Record<string, string> } {
  const i = css.indexOf('[data-theme="dark"]');
  const light = parseTokens(css.slice(0, i));
  const darkBlock = css.slice(i, css.indexOf("}", i));
  return { light, dark: { ...light, ...parseTokens(darkBlock) } };
}

// [foreground, background, minimum ratio, why]
export const REQUIRED_PAIRS: [string, string, number, string][] = [
  ["text", "bg", 4.5, "body text"],
  ["text", "surface", 4.5, "body text on cards"],
  ["text-2", "bg", 4.5, "secondary text"],
  ["text-2", "surface", 4.5, "secondary text on cards"],
  ["text-2", "sunken", 4.5, "secondary text on tracks"],
  ["text-3", "bg", 4.5, "captions"],
  ["text-3", "surface", 4.5, "captions on cards"],
  ["text-3", "sunken", 4.5, "captions on tracks"],
  ["primary", "bg", 4.5, "links"],
  ["primary", "surface", 4.5, "links on cards"],
  ["on-primary", "primary", 4.5, "primary button text"],
  ["mis-fg", "mis-bg", 4.5, "MISINFO / contradicted"],
  ["nomis-fg", "nomis-bg", 4.5, "NO-MISINFO / supported"],
  ["deb-fg", "deb-bg", 4.5, "DEBUNKED"],
  ["cr-fg", "cr-bg", 4.5, "CANNOT RECOGNIZE / insufficient"],
  ["cr-fg", "surface", 4.5, "insufficient (no fill)"],
  ["mix-fg", "mix-bg", 4.5, "mixed"],
  ["mis-fg", "surface", 4.5, "unsupported (no fill)"],
  ["warn-fg", "warn-bg", 4.5, "review / warning"],
  ["err-fg", "err-bg", 4.5, "system error"],
  ["input-border", "surface", 3, "form-control outline (1.4.11)"],
  ["input-border", "bg", 3, "form-control outline on page (1.4.11)"],
  ["mis-fg", "surface", 3, "unsupported dashed outline (1.4.11)"],
  ["primary", "surface", 3, "focus ring (2.4.13)"],
];
