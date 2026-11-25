// Single source of truth for every label, verdict, stance and status the UI shows.
// Internal enum values never reach the screen; components look up display text here.

export type VideoLabel = "MISINFO" | "NO_MISINFO" | "DEBUNKING" | "CANNOT_RECOGNIZE";
export type Stance = "ENDORSES" | "REFUTES" | "QUOTES" | "NEUTRAL" | "UNCLEAR";
export type Verdict = "SUPPORTED" | "CONTRADICTED" | "MIXED" | "INSUFFICIENT_EVIDENCE" | "NOT_VERIFIABLE";
export type ReviewStatus = "NOT_REQUIRED" | "PENDING" | "VERIFIED" | "CORRECTED" | "REJECTED";
export type JobState = "QUEUED" | "RUNNING" | "RETRYING" | "NEEDS_REVIEW" | "COMPLETED" | "FAILED";

type Meta = { display: string; description: string; icon: string; tone: string; dashed?: boolean };

export const LABELS: Record<VideoLabel, Meta> = {
  MISINFO:          { display: "MISINFO",          description: "Promotes a false or misleading health claim", icon: "alert",  tone: "misinfo" },
  NO_MISINFO:       { display: "NO-MISINFO",       description: "No false claim is promoted",                  icon: "checkc", tone: "nomisinfo" },
  DEBUNKING:        { display: "DEBUNKED",         description: "Raises a false claim in order to correct it", icon: "shield", tone: "debunked" },
  CANNOT_RECOGNIZE: { display: "CANNOT RECOGNIZE", description: "No reliable label could be reached",          icon: "helpc",  tone: "abstain", dashed: true },
};

// Direction 3 wording: describe the relationship to evidence, not truth.
export const VERDICTS: Record<Verdict, Meta> = {
  SUPPORTED:             { display: "Supported by evidence",   description: "Sources support the claim",                       icon: "checkc", tone: "nomisinfo" },
  CONTRADICTED:          { display: "Contradicted by evidence", description: "Sources contradict the claim",                    icon: "xc",     tone: "misinfo" },
  MIXED:                 { display: "Mixed evidence",           description: "Sources disagree",                                icon: "mixed",  tone: "mixed" },
  INSUFFICIENT_EVIDENCE: { display: "Insufficient evidence",    description: "No studies at the required level were found. Untested is not the same as false.", icon: "dashed", tone: "abstain", dashed: true },
  NOT_VERIFIABLE:        { display: "Not verifiable",           description: "Opinion, advice or prediction; no study could test it", icon: "ban", tone: "abstain" },
};

// Stance chips are deliberately colourless.
export const STANCES: Record<Stance, Omit<Meta, "tone">> = {
  ENDORSES: { display: "ENDORSES", description: "Presents the claim as true, in their own voice", icon: "endorse" },
  REFUTES:  { display: "REFUTES",  description: "Says the claim is wrong",                         icon: "refute" },
  QUOTES:   { display: "QUOTES",   description: "Reports someone else making the claim",           icon: "quote" },
  NEUTRAL:  { display: "NEUTRAL",  description: "Mentions the claim without taking a side",        icon: "minus" },
  UNCLEAR:  { display: "UNCLEAR",  description: "Position can't be determined (e.g. sarcasm)",     icon: "question", dashed: true },
};

export const REVIEW_STATUS: Record<ReviewStatus, { display: string; icon?: string }> = {
  NOT_REQUIRED: { display: "Not required" }, // not in the original brief: confirm with backend
  PENDING:   { display: "Pending review", icon: "clock" },
  VERIFIED:  { display: "Verified",       icon: "checkc" },
  CORRECTED: { display: "Corrected",      icon: "pencil" },
  REJECTED:  { display: "Rejected",       icon: "ban" },
};

export const JOB_STATES: Record<JobState, { display: string; icon: string }> = {
  QUEUED: { display: "Queued", icon: "clock" },
  RUNNING: { display: "Running", icon: "loader" },
  RETRYING: { display: "Retrying", icon: "refresh" },
  NEEDS_REVIEW: { display: "Needs review", icon: "flag" },
  COMPLETED: { display: "Completed", icon: "checkc" },
  FAILED: { display: "Failed", icon: "alert" },
};

// "What this means" line. Fixed copy, never model output.
// This is the main guard against reading DEBUNKED as MISINFO.
export function claimMeaning(stance: Stance, verdict: Verdict): string {
  const unsettled = verdict === "MIXED" || verdict === "INSUFFICIENT_EVIDENCE" || verdict === "NOT_VERIFIABLE";
  if (stance === "NEUTRAL" || stance === "UNCLEAR") return "The speaker's position on this claim is not clear.";
  const table: Record<"ENDORSES" | "REFUTES" | "QUOTES", [string, string, string]> = {
    //            CONTRADICTED                                                                     SUPPORTED                                              unsettled
    ENDORSES: ["The speaker promotes a claim that the evidence contradicts.",                    "The speaker states a claim the evidence supports.",   "The speaker promotes a claim no study settles."],
    REFUTES:  ["The speaker refutes a claim the evidence contradicts. This corrects misinformation.", "The speaker denies a claim the evidence supports.", "The speaker refutes a claim no study settles. A reviewer decides."],
    QUOTES:   ["The speaker reports someone else making a false claim.",                          "The speaker reports someone else's supported claim.", "The speaker reports a claim no study settles."],
  };
  const row = table[stance];
  return verdict === "CONTRADICTED" ? row[0] : verdict === "SUPPORTED" ? row[1] : unsettled ? row[2] : row[2];
}

// Evidence strip levels (Direction 3). Official guidance is a separate badge, not a level.
export const EVIDENCE_LEVELS = [
  { key: "SYSTEMATIC_REVIEW", short: "SR",  display: "Systematic review" },
  { key: "RCT",               short: "RCT", display: "Randomised trial" },
  { key: "OBSERVATIONAL",     short: "OBS", display: "Observational study" },
  { key: "ANIMAL_LAB",        short: "LAB", display: "Animal or lab study" },
] as const;
