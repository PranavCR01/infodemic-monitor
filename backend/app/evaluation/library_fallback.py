"""Is the offline library worth having? (target design §6: "Its value is measured, not
assumed: how often the fallback fires, and how often it changes a claim's verdict
compared with PubMed alone.")

- ``fallback_stats(states)``: over finished graph states, how many claims went to
  retrieval, how many fired the fallback (``library_evidence`` has the claim), and how
  many of those ended with a library passage in front of the verifier.
- ``verdict_changes(pubmed_only, with_library)``: per-claim verdicts from two runs of the
  same inputs, one without the library and one with it.
"""
from __future__ import annotations

from typing import Iterable, Mapping


def fallback_stats(states: Iterable[Mapping]) -> dict:
    claims = fired = kept = 0
    for st in states:
        searched = set(st.get("retrieved_evidence", {}))
        library = st.get("library_evidence", {})
        reranked = st.get("reranked_evidence", {})
        claims += len(searched)
        for cid in searched:
            if cid in library:
                fired += 1
                if any(e.source == "library" for e in reranked.get(cid, [])):
                    kept += 1
    return {
        "claims": claims,
        "fired": fired,
        "fire_rate": round(fired / claims, 4) if claims else 0.0,
        "fired_with_library_evidence_kept": kept,
    }


def verdict_changes(pubmed_only: Mapping[str, str], with_library: Mapping[str, str]) -> dict:
    shared = sorted(set(pubmed_only) & set(with_library))
    changes = [
        {"claim": c, "pubmed_only": pubmed_only[c], "with_library": with_library[c]}
        for c in shared
        if pubmed_only[c] != with_library[c]
    ]
    return {
        "compared": len(shared),
        "changed": len(changes),
        "change_rate": round(len(changes) / len(shared), 4) if shared else 0.0,
        "changes": changes,
    }
