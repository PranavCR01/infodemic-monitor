import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WHO Infodemic Monitor",
  description: "Health misinformation detection for short-form video",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">{children}</body>
    </html>
  );
}
