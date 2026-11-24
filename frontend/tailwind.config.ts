import type { Config } from "tailwindcss";

// From design/claude-design/starter/tailwind.config.ts. Colours point at the CSS
// variables in app/tokens.css, so dark mode is a data-theme switch.
const v = (name: string) => `var(--${name})`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: { DEFAULT: v("surface"), 2: v("surface-2"), sunken: v("sunken") },
        line: { DEFAULT: v("border"), strong: v("border-strong"), input: v("input-border") },
        ink: { DEFAULT: v("text"), 2: v("text-2"), 3: v("text-3"), "on-primary": v("on-primary") },
        primary: { DEFAULT: v("primary"), hover: v("primary-hover"), subtle: v("primary-subtle") },
        misinfo: { fg: v("mis-fg"), bg: v("mis-bg"), bd: v("mis-bd") },
        nomisinfo: { fg: v("nomis-fg"), bg: v("nomis-bg"), bd: v("nomis-bd") },
        debunked: { fg: v("deb-fg"), bg: v("deb-bg"), bd: v("deb-bd") },
        abstain: { fg: v("cr-fg"), bg: v("cr-bg"), bd: v("cr-bd") },
        mixed: { fg: v("mix-fg"), bg: v("mix-bg"), bd: v("mix-bd") },
        warn: { fg: v("warn-fg"), bg: v("warn-bg"), bd: v("warn-bd") },
        err: { fg: v("err-fg"), bg: v("err-bg"), bd: v("err-bd") },
        // Legacy colours used by the pre-design pages; removed once those pages are rebuilt.
        who: { blue: "#009edb", dark: "#0081b3" },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Noto Naskh Arabic", "Noto Serif SC", "Georgia", "serif"],
        sans: ["var(--font-sans)", "IBM Plex Sans Arabic", "IBM Plex Sans SC", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        display: ["32px", { lineHeight: "40px", fontWeight: "600" }],
        h1: ["24px", { lineHeight: "32px", fontWeight: "600" }],
        h2: ["18px", { lineHeight: "26px", fontWeight: "600" }],
        h3: ["15px", { lineHeight: "22px", fontWeight: "600" }],
        body: ["14px", { lineHeight: "22px" }],
        small: ["13px", { lineHeight: "20px" }],
        cap: ["12px", { lineHeight: "16px" }],
        transcript: ["17px", { lineHeight: "28px" }],
      },
      borderRadius: { sm: v("r-sm"), md: v("r-md"), lg: v("r-lg") },
      boxShadow: { 1: v("sh-1"), 2: v("sh-2"), 3: v("sh-3") },
      screens: { sm: "640px", md: "834px", lg: "1024px", xl: "1280px", "2xl": "1440px" },
    },
  },
  plugins: [],
};

export default config;
