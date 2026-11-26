// T52: "How we searched" as one plain-language finding, built by code from the stored
// search trail (T31) and the claim's sources. Never model text, and never the critic's
// pipeline notes ("search again", "search budget exhausted…"): those stay behind the
// review screen's technical details.
import type { Claim, ResultModel, Source } from "@/lib/api/result-adapter";

const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;

/** Sources the check saw but that neither supported nor contradicted the claim. */
export function unusedSources(c: Pick<Claim, "sources">): Source[] {
  return c.sources.filter((s) => s.relation === "CONSIDERED");
}

/**
 * One finding about the search for a claim, e.g. "No relevant study was found after 2
 * searches. 3 papers were retrieved and none was relevant enough to check the claim
 * against, so this claim could not be checked and was sent to a reviewer."
 * Counts distinct queries only. `sentToReviewer`: a review reason names this claim.
 */
export function searchFinding(c: Pick<Claim, "search" | "sources">, sentToReviewer: boolean): string | null {
  const s = c.search;
  if (!s) return null;
  const q = s.queries.length;
  const tested = c.sources.filter((x) => x.relation === "SUPPORTS" || x.relation === "CONTRADICTS");
  const against = tested.filter((x) => x.relation === "CONTRADICTS").length;
  const forIt = tested.length - against;
  const reviewer = sentToReviewer ? " and was sent to a reviewer" : "";
  const notChecked = `so this claim could not be checked${reviewer}.`;
  const after = q > 0 ? ` after ${n(q, "search", "searches")}` : "";
  const out: string[] = [];

  if (s.partial) {
    out.push(`This claim was searched with ${n(q, "query", "queries")}; this older analysis didn't record what each search returned.`);
  } else if (q > 0 && s.queries.every((x) => x.failed)) {
    out.push(`The study search failed each time it ran (${n(q, "search", "searches")}), ${notChecked}`);
  } else if (tested.length > 0) {
    const parts = [
      against ? `${against} ${against === 1 ? "contradicts" : "contradict"} it` : "",
      forIt ? `${forIt} ${forIt === 1 ? "supports" : "support"} it` : "",
    ].filter(Boolean);
    out.push(`${n(s.kept, "source was", "sources were")} checked against this claim${after}: ${parts.join(" and ")}.`);
    if (sentToReviewer) out.push("The claim was sent to a reviewer.");
  } else if (s.kept > 0) {
    out.push(
      `No relevant study was found${after}. ${n(s.kept, "source was", "sources were")} checked and none of them supported or contradicted the claim, ${notChecked}`,
    );
  } else if ((s.retrieved ?? s.screened) > 0) {
    const found = s.retrieved ?? s.screened;
    out.push(
      `No relevant study was found${after}. ${n(found, "paper was", "papers were")} retrieved and none was relevant enough to check the claim against, ${notChecked}`,
    );
  } else {
    out.push(`No study was found${after}, ${notChecked}`);
  }
  if (s.budgetExhausted && !s.partial) out.push(`The search used all ${s.roundsMax} rounds allowed for a claim.`);
  return out.join(" ");
}

/** Ids of the claims a review reason names (they were sent to a reviewer). */
export function flaggedClaimIds(r: Pick<ResultModel, "reasons" | "claims">): Set<string> {
  const numbers = new Set(r.reasons.map((x) => x.claimNumber).filter((x): x is number => x !== null));
  return new Set(r.claims.filter((c) => numbers.has(c.number)).map((c) => c.id));
}
