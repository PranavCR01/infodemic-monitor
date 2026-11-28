import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/jobs/mock-job-t65",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { ExportReport } from "@/components/export/ExportReport";
import { ClaimCard } from "@/components/result/ClaimCard";
import { REVIEW_REASONS, reasonRule, reasonText } from "@/lib/vocabulary";
import { MOCK_T65 } from "./mocks/t65";
import type { RawResult } from "./result-types";
import { adaptResult } from "./result-adapter";

// T70 (backend switch CLAIM_CONTEXT): "In context: ..." under each claim, and a
// screen-only claim quoted "On screen:", never "The speaker says:". Invented data.
const base = MOCK_T65.claims![0];
const SCREEN_TEXT = "10-20 µg in 1 application of 20 ppm product";
const WITH_CONTEXT: RawResult = {
  ...MOCK_T65,
  ocr_segments: [{ segment_id: "o10", source: "screen", start_seconds: 53.9, end_seconds: 59.8, text: SCREEN_TEXT }],
  claims: [
    {
      ...base,
      text: "Benzene doesn't get through skin easily",
      context: {
        scope: "specific",
        items: [{ field: "subject", label: "subject or product", text: "Benzoyl peroxide", segment_ids: ["o10"] }],
        setting_match: "different",
        softened: true,
      },
      context_text: "In context: subject or product: Benzoyl peroxide.",
      quote_source: "speech",
    },
    {
      ...base,
      claim_id: "c2",
      text: SCREEN_TEXT,
      deciding: false,
      modality: "screen",
      speaker_quote: null,
      stance_quotes: [],
      quote_source: "screen",
      screen_quote: SCREEN_TEXT,
    },
  ],
};

const exportOf = (raw: RawResult) =>
  render(<ExportReport r={adaptResult(raw)} recordUrl="https://monitor.example/jobs/x" />).container.textContent ?? "";

describe("T70 claim context", () => {
  it("adapts the context line, setting match and quote source", () => {
    const [c1, c2] = adaptResult(WITH_CONTEXT).claims;
    expect(c1.contextText).toBe("In context: subject or product: Benzoyl peroxide.");
    expect(c1.settingMatch).toBe("different");
    expect(c2.quoteSource).toBe("screen");
    expect(c2.speakerQuote).toEqual({ text: SCREEN_TEXT, at: c2.start, source: "screen" });
  });

  it("shows 'In context:' and 'On screen:' in the export, never 'The speaker says' for screen text", () => {
    const t = exportOf(WITH_CONTEXT);
    expect(t).toContain("In context: subject or product: Benzoyl peroxide.");
    expect(t).toContain(`On screen: ${SCREEN_TEXT}`);
    expect(t).not.toContain(`The speaker says: ${SCREEN_TEXT}`);
  });

  it("shows the context line on the claim card", () => {
    const c1 = adaptResult(WITH_CONTEXT).claims[0];
    const text = render(<ClaimCard claim={c1} active={false} onSelect={() => {}} onSeek={() => {}} onOpen={() => {}} />)
      .container.textContent;
    expect(text).toContain("In context: subject or product: Benzoyl peroxide.");
  });

  it("changes nothing for results without context", () => {
    const c = adaptResult(MOCK_T65).claims[0];
    expect(c.contextText).toBeNull();
    expect(c.quoteSource).toBeNull();
    expect(exportOf(MOCK_T65)).toContain("The speaker says:");
    expect(exportOf(MOCK_T65)).not.toContain("In context:");
  });

  it("explains the softened_by_context review reason", () => {
    expect(reasonRule("judge:softened_by_context:c1")).toBe("softened_by_context");
    expect(reasonText("judge:softened_by_context:c1")).toBe(REVIEW_REASONS.softened_by_context);
  });
});
