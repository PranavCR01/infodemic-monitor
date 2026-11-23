import type { Metadata } from "next";
import localFont from "next/font/local";
import "./tokens.css";
import "./globals.css";

// Self-hosted from @fontsource (latin subset, SIL Open Font License), so the build
// never fetches from Google Fonts: Vercel and CI build without that network access.
// Paths must be string literals: next/font reads them at build time.
const serif = localFont({
  src: [
    { path: "../node_modules/@fontsource/source-serif-4/files/source-serif-4-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/source-serif-4/files/source-serif-4-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-serif",
  display: "swap",
});
const sans = localFont({
  src: [
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2", weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-sans",
  display: "swap",
});
const mono = localFont({
  src: [
    { path: "../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WHO Infodemic Monitor",
  description: "Check what health videos claim, against what the evidence shows.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
