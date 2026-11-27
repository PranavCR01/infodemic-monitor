// The one source of display text for every label, verdict, stance, status and
// severity the UI shows. Internal enum values never reach the screen: components
// look up display text here, and text from the API passes through
// `displayText()` before it is rendered.
//
// Based on design/claude-design/starter/lib/vocabulary.ts, plus:
// - verdict UNSUPPORTED and `misinfo_basis` (decision D1 = B, design doc §7/§9);
// - severity HIGH / MEDIUM / LOW (§12: review priority only, never the label);
// - mappings from the backend's job states and review reasons.

export const VIDEO_LABELS = ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"] as const;
export const STANCE_VALUES = ["ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR"] as const;
export const VERDICT_VALUES = [
  "SUPPORTED",
  "CONTRADICTED",
  "MIXED",
  "INSUFFICIENT_EVIDENCE",
  "NOT_VERIFIABLE",
  "UNSUPPORTED",
] as const;
export const MISINFO_BASES = ["contradicted", "denies_supported", "unproven"] as const;
export const SEVERITIES = ["HIGH", "MEDIUM", "LOW"] as const;

export type VideoLabel = (typeof VIDEO_LABELS)[number];
export type Stance = (typeof STANCE_VALUES)[number];
export type Verdict = (typeof VERDICT_VALUES)[number];
export type MisinfoBasis = (typeof MISINFO_BASES)[number];
export type Severity = (typeof SEVERITIES)[number];
export type ReviewStatus = "NOT_REQUIRED" | "PENDING" | "VERIFIED" | "CORRECTED" | "REJECTED" | "REANALYSIS" | "SUPERSEDED";
export type JobState = "QUEUED" | "RUNNING" | "RETRYING" | "NEEDS_REVIEW" | "COMPLETED" | "FAILED";

/** Colour families. Each maps to one set of token classes in components/ui/tone.ts. */
export type Tone = "misinfo" | "nomisinfo" | "debunked" | "abstain" | "mixed" | "unsupported";

export type Meta = {
  display: string;
  description: string;
  icon: string;
  tone: Tone;
  dashed?: boolean;
};

export const LABELS: Record<VideoLabel, Meta> = {
  MISINFO: { display: "MISINFO", description: "Promotes a false or misleading health claim", icon: "alert", tone: "misinfo" },
  NO_MISINFO: { display: "NO-MISINFO", description: "No false claim is promoted", icon: "checkc", tone: "nomisinfo" },
  DEBUNKING: { display: "DEBUNKED", description: "Raises a false claim in order to correct it", icon: "shield", tone: "debunked" },
  CANNOT_RECOGNIZE: { display: "CANNOT RECOGNIZE", description: "No reliable label could be reached", icon: "helpc", tone: "abstain", dashed: true },
};

/** MISINFO is one label with a basis; the interface names the unproven case (D1 = B). */
export const MISINFO_BASIS: Record<MisinfoBasis, { suffix: string | null; description: string }> = {
  contradicted: { suffix: null, description: "Promotes a health claim the evidence contradicts" },
  denies_supported: { suffix: null, description: "Denies a health claim the evidence supports" },
  unproven: { suffix: "(unproven)", description: "Presents an untested remedy as working. No evidence supports it" },
};

/** Display name and description for a video label, taking the MISINFO basis into account. */
export function labelDisplay(label: VideoLabel, basis?: MisinfoBasis | null): { display: string; description: string } {
  const m = LABELS[label];
  if (label !== "MISINFO" || !basis) return { display: m.display, description: m.description };
  const b = MISINFO_BASIS[basis];
  return { display: b.suffix ? `${m.display} ${b.suffix}` : m.display, description: b.description };
}

// Direction 3 wording: describe the relationship to evidence, not truth.
export const VERDICTS: Record<Verdict, Meta> = {
  SUPPORTED: { display: "Supported by evidence", description: "Sources support the claim", icon: "checkc", tone: "nomisinfo" },
  CONTRADICTED: { display: "Contradicted by evidence", description: "Sources contradict the claim", icon: "xc", tone: "misinfo" },
  MIXED: { display: "Mixed evidence", description: "Sources disagree", icon: "mixed", tone: "mixed" },
  INSUFFICIENT_EVIDENCE: {
    display: "Insufficient evidence",
    description: "No studies at the required level were found. Untested is not the same as false.",
    icon: "dashed",
    tone: "abstain",
    dashed: true,
  },
  NOT_VERIFIABLE: { display: "Not verifiable", description: "Opinion, advice or prediction; no study could test it", icon: "ban", tone: "abstain" },
  // D1 = B. Not CONTRADICTED: the explanation always says "no evidence supports this", never "false".
  UNSUPPORTED: {
    display: "No supporting evidence",
    description: "A claim that something cures, treats or prevents an illness, with no evidence for it after a full search. Not proven false; the claim carries the burden of proof.",
    icon: "dashed",
    tone: "unsupported",
    dashed: true,
  },
};

// Stance chips are deliberately colourless: stance describes the speaker.
export const STANCES: Record<Stance, Omit<Meta, "tone">> = {
  ENDORSES: { display: "ENDORSES", description: "Presents the claim as true, in their own voice", icon: "endorse" },
  REFUTES: { display: "REFUTES", description: "Says the claim is wrong", icon: "refute" },
  QUOTES: { display: "QUOTES", description: "Reports someone else making the claim", icon: "quote" },
  NEUTRAL: { display: "NEUTRAL", description: "Mentions the claim without taking a side", icon: "minus" },
  UNCLEAR: { display: "UNCLEAR", description: "Position can't be determined (e.g. sarcasm)", icon: "question", dashed: true },
};

export const REVIEW_STATUS: Record<ReviewStatus, { display: string; icon: string }> = {
  NOT_REQUIRED: { display: "Not required", icon: "minus" }, // Q3: approved by the lead
  PENDING: { display: "Pending review", icon: "clock" },
  VERIFIED: { display: "Verified", icon: "checkc" },
  CORRECTED: { display: "Corrected", icon: "pencil" },
  REJECTED: { display: "Rejected", icon: "ban" },
  REANALYSIS: { display: "Re-analysis requested", icon: "refresh" },
  // T55: a deliberate re-analysis closed the open case; the new result is reviewed afresh.
  SUPERSEDED: { display: "Superseded by a newer analysis", icon: "refresh" },
};

/**
 * Backend review case → display status. No case on a finished job = "Not required".
 * T26 statuses: REVIEW_REQUIRED (open), VERIFIED, CORRECTED, REJECTED, REANALYSIS_REQUESTED.
 */
export function toReviewStatus(review: { status?: string | null; case_status?: string | null } | null | undefined): ReviewStatus {
  if (review?.case_status === "SUPERSEDED") return "SUPERSEDED";
  switch (review?.status) {
    case undefined:
    case null:
      return "NOT_REQUIRED";
    case "VERIFIED":
      return "VERIFIED";
    case "CORRECTED":
      return "CORRECTED";
    case "REJECTED":
      return "REJECTED";
    case "REANALYSIS_REQUESTED":
      return "REANALYSIS";
    case "SUPERSEDED":
      return "SUPERSEDED";
    default:
      // REVIEW_REQUIRED, and anything unknown: treat as still provisional.
      return "PENDING";
  }
}

export const JOB_STATES: Record<JobState, { display: string; icon: string }> = {
  QUEUED: { display: "Queued", icon: "clock" },
  RUNNING: { display: "Running", icon: "loader" },
  RETRYING: { display: "Retrying", icon: "refresh" },
  NEEDS_REVIEW: { display: "Needs review", icon: "flag" },
  COMPLETED: { display: "Completed", icon: "checkc" },
  FAILED: { display: "Failed", icon: "alert" },
};

// §12: severity orders the review queue. It never changes a label.
export const SEVERITY: Record<Severity, { display: string; icon: string; rank: number }> = {
  HIGH: { display: "High priority", icon: "flag", rank: 0 },
  MEDIUM: { display: "Medium priority", icon: "flag", rank: 1 },
  LOW: { display: "Low priority", icon: "minus", rank: 2 },
};

/**
 * One line under the label saying which rule reached it (Q6: CANNOT RECOGNIZE keeps
 * its name, with the reason underneath). Keys are the judge's decision rules (§9).
 */
export const DECISION_RULE_TEXT: Record<string, string> = {
  endorsed_contradicted: "The speaker promotes a claim the evidence contradicts.",
  refuted_supported: "The speaker denies a claim the evidence supports.",
  unproven: "The speaker presents an untested remedy as working, and no evidence supports it.",
  refuted_contradicted: "The speaker corrects a claim the evidence contradicts.",
  judged_nothing_false_endorsed: "Every claim the evidence could settle is supported or rejected correctly.",
  refuted_unsettled: "The speaker rejects a claim the evidence can't settle, so it may be a correction.",
  nothing_judged: "No claim in the video could be settled by the evidence found.",
  no_claims: "No checkable health claims were found in the video.",
  // T67 (3): the verifier failed for at least half of the checkable claims.
  analysis_incomplete: "The evidence check could not run for most of the claims, so the video could not be assessed.",
};

// ---------------------------------------------------------------- evidence levels

/** Evidence strip levels (Direction 3). Official guidance is a separate badge, not a level. */
export type EvidenceLevel = "SYSTEMATIC_REVIEW" | "RCT" | "OBSERVATIONAL" | "ANIMAL_LAB";

export const EVIDENCE_LEVEL_DISPLAY: Record<EvidenceLevel, { short: string; one: string; many: string }> = {
  SYSTEMATIC_REVIEW: { short: "SR", one: "systematic review", many: "systematic reviews" },
  RCT: { short: "RCT", one: "randomised trial", many: "randomised trials" },
  OBSERVATIONAL: { short: "OBS", one: "observational study", many: "observational studies" },
  ANIMAL_LAB: { short: "LAB", one: "animal or lab study", many: "animal or lab studies" },
};

/**
 * Backend study type (backend/app/core/retrieval/rerank.py StudyType) → strip level.
 * Guidelines count as official guidance, not a level. Clinical trials without
 * randomisation sit with observational studies. Narrative reviews, case reports,
 * opinion and unknown types have no level: they are listed, but not in the strip.
 */
export function evidenceLevel(studyType: string | null | undefined): EvidenceLevel | "GUIDANCE" | null {
  switch ((studyType ?? "").toLowerCase()) {
    case "systematic_review":
    case "meta_analysis":
      return "SYSTEMATIC_REVIEW";
    case "rct":
      return "RCT";
    case "clinical_trial":
    case "observational":
      return "OBSERVATIONAL";
    case "animal":
    case "in_vitro":
      return "ANIMAL_LAB";
    case "guideline":
      return "GUIDANCE";
    default:
      return null;
  }
}

export const STUDY_TYPE_DISPLAY: Record<string, string> = {
  systematic_review: "Systematic review",
  meta_analysis: "Meta-analysis",
  rct: "Randomised trial",
  guideline: "Guideline",
  clinical_trial: "Clinical trial",
  observational: "Observational study",
  narrative_review: "Narrative review",
  case_report: "Case report",
  animal: "Animal study",
  in_vitro: "Lab study",
  opinion: "Opinion or editorial",
  other: "Other",
  unknown: "Study type not recorded",
};

export function studyTypeDisplay(t: string | null | undefined): string {
  return STUDY_TYPE_DISPLAY[(t ?? "unknown").toLowerCase()] ?? STUDY_TYPE_DISPLAY.unknown;
}

/** Count wording per study type, for summaries built from the same field as the list (T65). */
const STUDY_TYPE_COUNT: Record<string, { one: string; many: string }> = {
  systematic_review: { one: "systematic review", many: "systematic reviews" },
  meta_analysis: { one: "meta-analysis", many: "meta-analyses" },
  rct: { one: "randomised trial", many: "randomised trials" },
  guideline: { one: "guideline", many: "guidelines" },
  clinical_trial: { one: "clinical trial", many: "clinical trials" },
  observational: { one: "observational study", many: "observational studies" },
  narrative_review: { one: "narrative review", many: "narrative reviews" },
  case_report: { one: "case report", many: "case reports" },
  animal: { one: "animal study", many: "animal studies" },
  in_vitro: { one: "lab study", many: "lab studies" },
  opinion: { one: "opinion piece", many: "opinion pieces" },
  other: { one: "other source", many: "other sources" },
  unknown: { one: "source without a recorded study type", many: "sources without a recorded study type" },
};

export function studyTypeCount(t: string | null | undefined, n: number): string {
  const w = STUDY_TYPE_COUNT[(t ?? "unknown").toLowerCase()] ?? STUDY_TYPE_COUNT.unknown;
  return `${n} ${n === 1 ? w.one : w.many}`;
}

/** The key a study type is counted under: unknown and unrecognised values together. */
export function studyTypeKey(t: string | null | undefined): string {
  const k = (t ?? "unknown").toLowerCase();
  return k in STUDY_TYPE_COUNT ? k : "unknown";
}

// ---------------------------------------------------------------- parsing

const has = <T extends string>(values: readonly T[], v: unknown): v is T =>
  typeof v === "string" && (values as readonly string[]).includes(v);

export const isVideoLabel = (v: unknown): v is VideoLabel => has(VIDEO_LABELS, v);
export const isStance = (v: unknown): v is Stance => has(STANCE_VALUES, v);
export const isVerdict = (v: unknown): v is Verdict => has(VERDICT_VALUES, v);
export const isMisinfoBasis = (v: unknown): v is MisinfoBasis => has(MISINFO_BASES, v);
export const isSeverity = (v: unknown): v is Severity => has(SEVERITIES, v);

/**
 * Backend job status → display state. Covers today's five states and the §1 states
 * T28 adds. REJECTED is a review outcome: the job itself is finished.
 * Unknown values return null; callers show "Unknown state", never the raw value.
 */
export function toJobState(status: string | null | undefined): JobState | null {
  switch (status) {
    case "PENDING":
    case "QUEUED":
      return "QUEUED";
    case "STARTED":
    case "RUNNING":
      return "RUNNING";
    case "RETRY_PENDING":
    case "RETRYING":
      return "RETRYING";
    case "REVIEW_REQUIRED":
      return "NEEDS_REVIEW";
    case "SUCCESS":
    case "COMPLETED":
    case "REJECTED":
      return "COMPLETED";
    case "FAILED":
      return "FAILED";
    default:
      return null;
  }
}

// ---------------------------------------------------------------- review reasons

/**
 * Plain-language text per review-reason rule (`rule:detail`). T26 will send this
 * text from the backend; until then, and as a fallback, the UI uses this table.
 * Unknown rules get a generic sentence, never the code.
 */
export const REVIEW_REASONS: Record<string, string> = {
  weak_evidence: "The evidence is too weak to decide this claim.",
  conflicting_evidence: "Studies point in different directions on this claim.",
  weak_study_types: "Only weak kinds of study were found for this claim.",
  unclear_stance: "It isn't clear whether the speaker supports or rejects this claim.",
  critic_escalated: "The system's own check asked for a person to look.",
  budget_exhausted: "The search stopped before it could finish checking this claim.",
  validation_failed: "The result failed an automatic consistency check.",
  low_confidence: "The system's confidence is low.",
  high_risk_uncertain: "A high-risk claim the evidence couldn't settle.",
  unproven_claim: "A remedy is presented as working, and no evidence supports it.",
  user_requested: "Someone asked for a person to check this result.",
  prompt_injection_suspected: "The video may contain text trying to steer the analysis.",
  guardrail: "A safety check stopped part of the analysis.",
  // T37: video-level, no claim id. LOW priority.
  nothing_judged: "No claim in this video could be checked against the evidence.",
  // T64 (f): video-level, no claim id; the label is unchanged.
  main_claims_unchecked:
    "The label rests on side claims: at least half of the treatment and prevention claims the speaker makes could not be checked against the evidence.",
  // T67 (1): per claim. Off by default (failed the T67 replay gate); text kept so the reason reads plainly if switched on.
  second_check_disagreed:
    "A second automated check still disagreed with this claim's verdict when its attempts ran out; the verdict was kept for a person to confirm.",
  // T67 (3): video-level, no claim id; the label is CANNOT RECOGNIZE.
  analysis_incomplete:
    "The evidence check could not run for at least half of the claims, so the video could not be assessed. It should be checked or analysed again.",
  // T67 (2): judge:thin_contradiction:<cid>. Off by default (failed the T67 replay gate).
  thin_contradiction:
    "The evidence against this claim is too thin to decide the label on its own: fewer than two papers on its topic and no review, trial or guideline.",
  // judge:<flag>
  mixed_video: "The video both spreads and corrects false claims.",
  unclear_stance_contradicted: "A false claim is made, but the speaker's position on it is unclear.",
  false_claim_not_refuted: "A false claim is mentioned and not corrected.",
  mixed_evidence: "Studies disagree on a claim that decides the label.",
  verification_failed: "A claim couldn't be checked against the evidence.",
  denies_supported: "The speaker denies something the evidence supports.",
  possible_debunk: "The speaker may be correcting a claim the evidence can't settle.",
};

const GENERIC_REASON = "Flagged for a person to check.";

/** The rule name of a stored reason: `weak_evidence:c1` → weak_evidence; `judge:possible_debunk:c2` → possible_debunk. */
export function reasonRule(code: string): string {
  const [head, rest] = [code.split(":")[0], code.split(":").slice(1)];
  return head === "judge" && rest.length > 0 ? rest[0] : head;
}

export function reasonText(code: string): string {
  return REVIEW_REASONS[reasonRule(code)] ?? GENERIC_REASON;
}

// ---------------------------------------------------------------- "what this means"

/**
 * The fixed "what this means" line for a claim. Never model output: this is the
 * main guard against reading DEBUNKED as MISINFO.
 */
export function claimMeaning(stance: Stance, verdict: Verdict): string {
  if (stance === "NEUTRAL" || stance === "UNCLEAR") return "The speaker's position on this claim is not clear.";
  if (verdict === "UNSUPPORTED") {
    return {
      ENDORSES: "The speaker presents an untested remedy as working. No evidence supports it.",
      REFUTES: "The speaker rejects a claim no evidence supports.",
      QUOTES: "The speaker reports someone else's claim that no evidence supports.",
    }[stance];
  }
  const table: Record<"ENDORSES" | "REFUTES" | "QUOTES", [string, string, string]> = {
    //        CONTRADICTED, SUPPORTED, unsettled (MIXED / INSUFFICIENT_EVIDENCE / NOT_VERIFIABLE)
    ENDORSES: [
      "The speaker promotes a claim that the evidence contradicts.",
      "The speaker states a claim the evidence supports.",
      "The speaker promotes a claim no study settles.",
    ],
    REFUTES: [
      "The speaker refutes a claim the evidence contradicts. This corrects misinformation.",
      "The speaker denies a claim the evidence supports.",
      "The speaker refutes a claim no study settles. A reviewer decides.",
    ],
    QUOTES: [
      "The speaker reports someone else making a false claim.",
      "The speaker reports someone else's supported claim.",
      "The speaker reports a claim no study settles.",
    ],
  };
  const row = table[stance];
  if (verdict === "CONTRADICTED") return row[0];
  if (verdict === "SUPPORTED") return row[1];
  return row[2];
}

// ---------------------------------------------------------------- research dashboard (T62)

/** Always shown on the dashboard (queue row T62, §7ah `note`). */
export const DASHBOARD_NOTE = "These figures describe videos uploaded to this tool, not how common misinformation is online.";

export const STATS_WINDOWS = ["7d", "30d", "90d", "all"] as const;
export type StatsWindow = (typeof STATS_WINDOWS)[number];
export const STATS_WINDOW_DISPLAY: Record<StatsWindow, string> = { "7d": "7 days", "30d": "30 days", "90d": "90 days", all: "All time" };

/** How a MISINFO label was reached, for the dashboard split. `unspecified` = not recorded (older results). */
export const MISINFO_BASIS_DISPLAY: Record<MisinfoBasis | "unspecified", string> = {
  contradicted: "Evidence contradicts the claim",
  unproven: "Unproven remedy presented as working",
  denies_supported: "Denies a claim the evidence supports",
  unspecified: "Basis not recorded (older results)",
};

/** Claim categories from the extraction prompt (extract_v4). */
export const CLAIM_CATEGORY_DISPLAY: Record<string, string> = {
  treatment_efficacy: "Treatment works",
  prevention: "Prevention",
  causation: "Cause of illness",
  safety: "Safety",
  diagnosis: "Diagnosis",
  nutrition: "Nutrition",
  statistic: "Statistics",
  evidence_meta: "About the evidence itself",
  other: "Other",
};

export function categoryDisplay(c: string): string {
  const k = c.toLowerCase();
  if (CLAIM_CATEGORY_DISPLAY[k]) return CLAIM_CATEGORY_DISPLAY[k];
  const words = k.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Unnamed";
}


// ---------------------------------------------------------------- free text from the API

const ENUM_DISPLAY: [RegExp, string][] = [
  [/\bCANNOT_RECOGNIZE\b/g, LABELS.CANNOT_RECOGNIZE.display],
  [/\bNO_MISINFO\b/g, LABELS.NO_MISINFO.display],
  [/\bDEBUNKING\b/g, LABELS.DEBUNKING.display],
  [/\bINSUFFICIENT_EVIDENCE\b/g, VERDICTS.INSUFFICIENT_EVIDENCE.display.toLowerCase()],
  [/\bNOT_VERIFIABLE\b/g, VERDICTS.NOT_VERIFIABLE.display.toLowerCase()],
  [/\bREVIEW_REQUIRED\b/g, "needs review"],
];

/**
 * Safety net for text written by the backend (explanations, limitations). The
 * backend's template explanation can start with an internal enum such as
 * "CANNOT_RECOGNIZE: …"; this swaps known enum tokens for their display names.
 * It does not rewrite meaning, and it is not a substitute for fixing the source.
 */
export function displayText(text: string | null | undefined): string {
  if (!text) return "";
  return ENUM_DISPLAY.reduce((s, [re, rep]) => s.replace(re, rep), text);
}

// ---------------------------------------------------------------- evaluations (T63, admin only)

/** Plain names for the pipeline's graph steps (backend app/evaluation/registry.py PIPELINE_STEPS). */
export const PIPELINE_STEP_DISPLAY: Record<string, string> = {
  load_artifacts: "Load video",
  transcribe_audio: "Transcribe speech",
  extract_ocr: "Read on-screen text",
  fuse_modalities: "Combine speech and text",
  extract_claims: "Find health claims",
  analyze_stance: "Read the speaker's stance",
  plan_retrieval: "Plan the search",
  retrieve_evidence: "Search for evidence",
  rerank_evidence: "Rank the evidence",
  verify_claims: "Check claims against evidence",
  critique_verification: "Second check of the verdicts",
  judge_classification: "Decide the video's label",
  validate_result: "Validate the result",
  route_for_review: "Send to a reviewer",
  human_review: "Reviewer decision",
  persist_result: "Save the result",
};

export function stepDisplay(step: string): string {
  return PIPELINE_STEP_DISPLAY[step] ?? step.replace(/_/g, " ");
}

export type EvalSplit = "tune" | "test" | "none";

/** Every tune-split result carries this label (T63): development numbers, not product accuracy. */
export const EVAL_SPLIT_DISPLAY: Record<EvalSplit, { short: string; label: string }> = {
  tune: { short: "Tune", label: "Development (tune split): not product accuracy" },
  test: { short: "Test", label: "Held-out test split" },
  none: { short: "Not a golden split", label: "Not one golden-set split (see notes)" },
};

export const SYNTHETIC_DISPLAY = "Synthetic data: shows how it works, not real accuracy";
