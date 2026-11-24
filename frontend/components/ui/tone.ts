import type { Tone } from "@/lib/vocabulary";

// Literal class strings so Tailwind's scanner finds them.
export const TONE: Record<Tone, string> = {
  misinfo: "text-misinfo-fg bg-misinfo-bg border-misinfo-bd",
  nomisinfo: "text-nomisinfo-fg bg-nomisinfo-bg border-nomisinfo-bd",
  debunked: "text-debunked-fg bg-debunked-bg border-debunked-bd",
  abstain: "text-abstain-fg bg-abstain-bg border-abstain-bd",
  mixed: "text-mixed-fg bg-mixed-bg border-mixed-bd",
  // D1 = B: drives a MISINFO label, so rust; no fill and a dashed rust outline, so it
  // never reads as a filled CONTRADICTED chip, nor as the grey of INSUFFICIENT EVIDENCE.
  unsupported: "text-misinfo-fg bg-transparent border-misinfo-fg",
};
