// T65: text fixes shared by the result page and the exported report. Pure functions,
// applied once in the result adapter, so both surfaces get the same words.

/** A source as these helpers need it. */
export type NamedSource = { id: string; title: string; pmid: string | null };

/** "A review." → "A review" (titles get their own full stop when printed: no "review.. 2016"). */
export function cleanTitle(title: string | null | undefined): string {
  return (title ?? "").trim().replace(/[.\s]+$/, "");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-05" → "5 Nov 2026", "2026-11" → "Nov 2026", "2026" → "2026"; anything else → null. */
export function formatPubDate(d: string | null | undefined): string | null {
  const m = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec((d ?? "").trim());
  if (!m) return null;
  const [, y, mo, day] = m;
  if (!mo) return y;
  const month = Number(mo);
  if (month < 1 || month > 12) return y;
  if (!day) return `${MONTHS[month - 1]} ${y}`;
  const dn = Number(day);
  return dn >= 1 && dn <= 31 ? `${dn} ${MONTHS[month - 1]} ${y}` : `${MONTHS[month - 1]} ${y}`;
}

/** Short name for a source inside a sentence: its title (cut at a word near 60 characters), else "PMID n". */
export function shortSourceName(s: NamedSource): string {
  const t = cleanTitle(s.title);
  // An untitled source already carries "PMID n" as its title: no quotes around it.
  if (t && !/^PMID \d+$/.test(t)) {
    if (t.length <= 60) return `“${t}”`;
    const cut = t.slice(0, 60).replace(/\s+\S*$/, "");
    return `“${cut || t.slice(0, 60)}…”`;
  }
  return s.pmid ? `PMID ${s.pmid}` : "one of the sources";
}

// Internal evidence ids: ev_ followed by letters, digits, "_" or "-" (e.g. ev_3f9a1c, ev_c1_2).
const EV_ID = /\bev_[A-Za-z0-9][A-Za-z0-9_-]*/g;

/** Replace internal evidence ids (ev_…) with the source's short title or PMID. Unknown ids read "one of the sources". */
export function replaceEvidenceIds(text: string, sources: NamedSource[]): string {
  if (!text || !text.includes("ev_")) return text;
  const byId = new Map(sources.map((s) => [s.id, s]));
  return text
    .replace(EV_ID, (id) => {
      const s = byId.get(id);
      return s ? shortSourceName(s) : "one of the sources";
    })
    .replace(/\[(“[^”]*”|PMID \d+|one of the sources)\]/g, "$1");
}

/**
 * The second automated check (the critic) is not a person: text that calls it "the
 * reviewer" is reworded. Only used on claim-level verifier and critic text, where
 * "reviewer" can only mean that check.
 */
export function secondCheckWording(text: string): string {
  if (!text) return text;
  return text
    .replace(/\bThe reviewer's\b/g, "The second automated check's")
    .replace(/\bthe reviewer's\b/g, "the second automated check's")
    .replace(/\bThe reviewer\b/g, "A second automated check")
    .replace(/\bthe reviewer\b/g, "a second automated check")
    .replace(/\bReviewer notes?\b/g, (m) => (m.endsWith("s") ? "Second-check notes" : "Second-check note"));
}

/** Claim-level model text: ev_ ids out, the critic named for what it is. */
export function cleanClaimText(text: string, sources: NamedSource[]): string {
  return secondCheckWording(replaceEvidenceIds(text, sources));
}
