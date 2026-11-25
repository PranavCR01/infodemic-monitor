import {
  EmptyState,
  ErrorBanner,
  JobStateTag,
  LabelBadge,
  ReviewBanner,
  ReviewReasonChip,
  ReviewStatusTag,
  SeverityTag,
  StanceChip,
  VerdictChip,
  WarnBanner,
} from "@/components/ui";
import {
  claimMeaning,
  REVIEW_STATUS,
  SEVERITIES,
  STANCE_VALUES,
  VERDICT_VALUES,
  VIDEO_LABELS,
  type ReviewStatus,
} from "@/lib/vocabulary";

export const metadata = { title: "Components · WHO Infodemic Monitor" };

// Reference page for the design system (chunk 1). Signed-in users only (middleware).
export default function ComponentsPage() {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 px-4 py-10 md:px-8">
      <header>
        <p className="text-cap font-semibold uppercase tracking-wider text-ink-3">Design system</p>
        <h1 className="font-serif text-display text-ink">Components</h1>
        <p className="text-small text-ink-2">Every label, verdict, stance and status is icon + text. Stance chips have no colour.</p>
      </header>

      <Section title="Video labels">
        <div className="flex flex-wrap gap-6">
          {VIDEO_LABELS.map((l) => (
            <LabelBadge key={l} label={l} size="lg" showDescription />
          ))}
          <LabelBadge label="MISINFO" basis="unproven" size="lg" showDescription />
        </div>
        <div className="flex flex-wrap gap-3">
          {VIDEO_LABELS.map((l) => (
            <LabelBadge key={l} label={l} />
          ))}
        </div>
      </Section>

      <Section title="Evidence verdicts">
        <div className="flex flex-wrap gap-3">
          {VERDICT_VALUES.map((v) => (
            <VerdictChip key={v} verdict={v} />
          ))}
        </div>
      </Section>

      <Section title="Speaker stance">
        <div className="flex flex-wrap gap-3">
          {STANCE_VALUES.map((s) => (
            <StanceChip key={s} stance={s} />
          ))}
        </div>
      </Section>

      <Section title="What this means (fixed copy)">
        <table className="w-full border-collapse text-small">
          <thead>
            <tr className="border-b border-line text-left text-ink-2">
              <th scope="col" className="py-2 pr-4 font-semibold">Stance</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Verdict</th>
              <th scope="col" className="py-2 font-semibold">Line shown</th>
            </tr>
          </thead>
          <tbody>
            {(["ENDORSES", "REFUTES", "QUOTES"] as const).flatMap((s) =>
              (["CONTRADICTED", "SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"] as const).map((v) => (
                <tr key={s + v} className="border-b border-line">
                  <td className="py-2 pr-4"><StanceChip stance={s} /></td>
                  <td className="py-2 pr-4"><VerdictChip verdict={v} /></td>
                  <td className="py-2">{claimMeaning(s, v)}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </Section>

      <Section title="Statuses">
        <div className="flex flex-wrap gap-6">
          {(Object.keys(REVIEW_STATUS) as ReviewStatus[]).map((s) => (
            <ReviewStatusTag key={s} status={s} />
          ))}
        </div>
        <div className="flex flex-wrap gap-6">
          {["PENDING", "STARTED", "RETRY_PENDING", "REVIEW_REQUIRED", "SUCCESS", "FAILED"].map((s) => (
            <JobStateTag key={s} status={s} />
          ))}
        </div>
        <div className="flex flex-wrap gap-6">
          {SEVERITIES.map((s) => (
            <SeverityTag key={s} severity={s} />
          ))}
        </div>
      </Section>

      <Section title="Banners and states">
        <ReviewBanner>
          <ReviewReasonChip code="judge:possible_debunk:c2" />
          <ReviewReasonChip code="unproven_claim:c1" />
        </ReviewBanner>
        <WarnBanner title="Temporary problem, retrying automatically.">Attempt 2 of 3.</WarnBanner>
        <ErrorBanner title="The upload stopped.">Nothing was analysed. Your file is still on your device.</ErrorBanner>
        <EmptyState title="Nothing to review">New cases appear here when the system sends a video for review.</EmptyState>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6 shadow-1">
      <h2 className="text-h2 text-ink">{title}</h2>
      {children}
    </section>
  );
}
