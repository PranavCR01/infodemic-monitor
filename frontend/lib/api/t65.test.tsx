import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/jobs/mock-job-t65",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { ExportReport } from "@/components/export/ExportReport";
import { ClaimCard } from "@/components/result/ClaimCard";
import { ClaimDrawer } from "@/components/result/ClaimDrawer";
import { SourceCard } from "@/components/result/SourceCard";
import { EVIDENCE_LEVEL_DISPLAY } from "@/lib/vocabulary";
import { MOCK_T65, MOCK_T65_OLD } from "./mocks/t65";
import { adaptResult, evidenceText, sourceMeta } from "./result-adapter";

const r = adaptResult(MOCK_T65);
const old = adaptResult(MOCK_T65_OLD);
const c1 = r.claims[0];
const exportOf = (raw = MOCK_T65) => render(<ExportReport r={adaptResult(raw)} recordUrl="https://monitor.example/jobs/x" />).container.textContent ?? "";
const card = (claim = c1) => render(<ClaimCard claim={claim} active={false} onSelect={() => {}} onSeek={() => {}} onOpen={() => {}} />).container.textContent ?? "";

describe("T65 (a) no internal evidence ids", () => {
  it("are replaced in claim text, limitations, critic notes, reasons and the explanation", () => {
    const texts = [r.explanation, c1.verdictExplanation, ...c1.limitations, ...c1.criticNotes, c1.stanceRationale, ...r.reasons.map((x) => x.text)];
    for (const t of texts) expect(t).not.toMatch(/ev_/);
    expect(c1.verdictExplanation).toContain("“Late vitamin K deficiency bleeding in an infant whose…”");
    expect(c1.limitations[0]).toContain("PMID 00000103");
    expect(r.explanation).toContain("“Vitamin K prophylaxis in newborns: a narrative review”");
  });

  it("appear nowhere on the claim card or in the export", () => {
    expect(card()).not.toMatch(/ev_/);
    expect(exportOf()).not.toMatch(/ev_/);
  });
});

describe("T65 (b) the second automated check is not 'the reviewer'", () => {
  it("is reworded in verifier and critic text", () => {
    expect(c1.verdictExplanation).toContain("A second automated check noted the review is old");
    expect(c1.limitations[0]).toMatch(/^The second automated check's note/);
    expect(c1.criticNotes[0]).toMatch(/^A second automated check would like a trial/);
  });

  it("never reads 'the reviewer' on the card or in the export", () => {
    expect(card()).not.toMatch(/\bthe reviewer\b/i);
    expect(exportOf()).not.toMatch(/\bthe reviewer\b/i);
  });
});

describe("T65 (c) one source of truth for study type", () => {
  it("summarises unlevelled sources by the study type the list shows", () => {
    const text = evidenceText(c1.evidence, EVIDENCE_LEVEL_DISPLAY);
    expect(text).toBe("2 case reports against · 1 narrative review against");
    expect(text).not.toMatch(/without a (recorded )?study type/);
  });

  it("the export's summary and source list agree", () => {
    const t = exportOf();
    expect(t).toContain("2 case reports against · 1 narrative review against");
    expect(t.match(/Case report\./g)).toHaveLength(2);
    expect(t.match(/Narrative review\./g)).toHaveLength(1);
  });

  it("still says so when a study type really is missing", () => {
    const raw = { ...MOCK_T65, claims: [{ ...MOCK_T65.claims![0], evidence: MOCK_T65.claims![0].evidence!.map((e) => ({ ...e, study_type: null })) }] };
    expect(evidenceText(adaptResult(raw).claims[0].evidence, EVIDENCE_LEVEL_DISPLAY)).toBe("3 sources without a recorded study type against");
  });
});

describe("T65 (d) no double full stop", () => {
  it("strips a title's trailing full stop", () => {
    expect(c1.sources.map((s) => s.title)).toContain("Vitamin K prophylaxis in newborns: a narrative review");
  });

  it("prints 'title. journal, date.' with one full stop each", () => {
    const t = exportOf();
    expect(t).not.toMatch(/\.\./);
    expect(t).toContain("Vitamin K prophylaxis in newborns: a narrative review. Pediatrics, Nov 2016. Narrative review.");
  });

  it("names an untitled source by its PMID, unquoted and printed once", () => {
    expect(c1.sources.find((s) => s.id === "ev_k3")!.title).toBe("PMID 00000103");
    expect(c1.limitations[0]).toContain("(PMID 00000103)");
    expect(exportOf()).toContain("PMID 00000103. 2019. Case report. Contradicts. ");
    expect(exportOf().match(/PMID 00000103/g)).toHaveLength(2); // limitation + source line
  });
});

describe("T65 (e) the speaker quote", () => {
  it("is speaker_quote as given, with its segment's time", () => {
    expect(c1.speakerQuote).toEqual({ text: "A JAMA study published November 5th showed the vitamin K shot is unnecessary.", at: 4, source: "speech" });
    const t = card();
    expect(t).toContain("A JAMA study published November 5th");
    expect(t).not.toContain("welcome back");
    expect(t).toContain("(0:04)");
    expect(exportOf()).toContain("The speaker says: A JAMA study published November 5th");
  });

  it("leads the claim drawer's quotes", () => {
    render(<ClaimDrawer claims={r.claims} openId="c1" transcript={r.transcript} onNavigate={() => {}} onClose={() => {}} onPlay={() => {}} />);
    const quotes = screen.getAllByText(/welcome back|JAMA study published/);
    expect(quotes[0]).toHaveTextContent("A JAMA study published November 5th");
    expect(quotes[1]).toHaveTextContent("welcome back");
  });

  it("falls back to the first stance quote on older results", () => {
    expect(old.claims[0].speakerQuote).toEqual({ text: "Hi everyone, welcome back.", at: 0, source: "speech" });
  });

  it("uses the claim's start when the quote matches no segment", () => {
    const raw = { ...MOCK_T65, claims: [{ ...MOCK_T65.claims![0], speaker_quote: "the vitamin K shot is unnecessary" }] };
    const c = adaptResult(raw).claims[0];
    expect(c.speakerQuote).toEqual({ text: "the vitamin K shot is unnecessary", at: null, source: null });
    expect(card(c)).toContain("(0:00)");
  });
});

describe("T65 (f) journal and publication date", () => {
  it("formats the date and shows the journal in the source line", () => {
    const [k1, k2, k3] = c1.sources;
    expect(sourceMeta(k1)).toEqual(["J Pediatr", "5 Mar 2021"]);
    expect(sourceMeta(k2)).toEqual(["Pediatrics", "Nov 2016"]);
    expect(sourceMeta(k3)).toEqual(["2019"]);
  });

  it("renders on the source card, and hides when null", () => {
    const { container } = render(<SourceCard s={c1.sources[0]} />);
    expect(within(container).getByText("J Pediatr · 5 Mar 2021")).toBeInTheDocument();
    render(<SourceCard s={c1.sources[2]} />);
    expect(screen.getByText("2019")).toBeInTheDocument();
  });

  it("older results without the fields still show publisher and year", () => {
    const s = old.claims[0].sources[0];
    expect(s.journal).toBeNull();
    expect(s.pubDate).toBeNull();
    expect(sourceMeta(s)).toEqual(["[Journal]", "2021"]);
    expect(exportOf(MOCK_T65_OLD)).toContain("[Journal], 2021.");
  });
});
