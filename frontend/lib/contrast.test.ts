import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { contrast, REQUIRED_PAIRS, themes } from "./contrast";

const css = readFileSync(join(__dirname, "..", "app", "tokens.css"), "utf8");
const t = themes(css);

describe("contrast()", () => {
  it("matches known WCAG values", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
  });
});

describe.each(["light", "dark"] as const)("%s tokens meet WCAG AA", (theme) => {
  it.each(REQUIRED_PAIRS)("%s on %s ≥ %s (%s)", (fg, bg, min) => {
    const tokens = t[theme];
    expect(tokens[fg], `missing --${fg}`).toBeDefined();
    expect(tokens[bg], `missing --${bg}`).toBeDefined();
    expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min);
  });
});
