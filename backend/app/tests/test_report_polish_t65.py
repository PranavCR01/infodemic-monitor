"""T65: report and result-page polish (backend), on the real rows of production job d2bf4179.

``fixtures/prod_d2bf4179/vitamin_k_rerun.real.json`` is the vitamin K re-analysis copied
from production (public video content only). Each problem the exported report showed is
checked on those rows:

(a) evidence ids (``ev_…``) in explanations: c7's stored explanation;
(b) "The reviewer was right …" in limitations: c11 and c14;
(c) "6 sources without a study type" next to listed types: c7 cites 4 narrative
    reviews and 2 case reports;
(d) "review.. 2016": PubMed titles end with a full stop;
(e) the quote was the first segment of the span, not the words of the claim;
(f) journal and publication date: the JAMA paper (PMID 42986716) c2 cites.

No model calls: the verifier is a scripted fake; PubMed comes from recorded EFetch XML.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.graph import verifier as vf
from app.core.graph.state import CriticDecision, CriticResult, GraphClaim, Verdict
from app.core.retrieval.pubmed import PubMedArticle, parse_efetch
from app.core.retrieval.retriever import to_evidence
from app.core.retrieval.schemas import EvidenceRecord
from app.core.speaker_quote import QuoteSegment, best_overlap_quote
from app.core.user_text import (
    clean_title,
    has_evidence_ids,
    mentions_reviewer,
    render_evidence_ids,
    reword_reviewer,
    short_title,
    source_line,
    source_name,
)
from app.db.models.claim import (
    ClaimEvidenceRow,
    ClaimRow,
    ClaimStanceRow,
    EvidenceRecordRow,
    VerificationResultRow,
)
from app.services import result_view_service as rv
from app.services.pipeline_result_service import _with_source_meta

FIX = Path(__file__).parent / "fixtures"
REAL = FIX / "prod_d2bf4179" / "vitamin_k_rerun.real.json"
JAMA_XML = FIX / "find_study" / "efetch" / "42986716.xml"


def jama_article() -> PubMedArticle:
    xml = JAMA_XML.read_text()
    if "<PubmedArticleSet" not in xml:  # the recorded file holds the article element only
        xml = "<PubmedArticleSet>" + xml.split("?>", 1)[-1] + "</PubmedArticleSet>"
    return parse_efetch(xml)[0]


@pytest.fixture(scope="module")
def job() -> dict:
    return json.loads(REAL.read_text())


def claim(job: dict, cid: str) -> dict:
    return next(c for c in job["claims"] if c["claim_id"] == cid)


def records(c: dict) -> list[EvidenceRecord]:
    return [EvidenceRecord(evidence_id=f"ev_{e['pmid']}", source="pubmed", pmid=e["pmid"], title=e["title"],
                           publication_year=e.get("year"), publication_type=list(e.get("publication_type") or []),
                           study_type=e.get("study_type"))
            for e in c["evidence"]]


def graph_claim(c: dict) -> GraphClaim:
    return GraphClaim(claim_id=c["claim_id"], claim_text=c["text"], claim_category=c["category"],
                      claim_kind=c["claim_kind"], source_segment_ids=["t1"],
                      start_seconds=c["start_seconds"], end_seconds=c["end_seconds"])


def stored_answer(c: dict) -> dict:
    rel = lambda r: [f"ev_{e['pmid']}" for e in c["evidence"] if e.get("relation") == r]  # noqa: E731
    return {"verdict": c["verdict"], "supporting_evidence_ids": rel("SUPPORTS"),
            "contradicting_evidence_ids": rel("CONTRADICTS"), "explanation": c["explanation"],
            "limitations": list(c["limitations"]), "raw_confidence": 0.7}


class Scripted:
    """Returns the given answers in order (the last one repeats)."""

    def __init__(self, *answers: dict):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def call(self, step, input, *, system=None):
        self.prompts.append(input["messages"][0]["content"])
        out = self.answers[min(len(self.prompts), len(self.answers)) - 1]
        return SimpleNamespace(output=out, record=SimpleNamespace(model="fake", prompt_version="verify_v3"))


def claim_row(c: dict, job: dict) -> ClaimRow:
    """A transient (not persisted) claim row built from the stored production row."""
    row = ClaimRow(id=f"row-{c['claim_id']}", job_id="d2bf4179", claim_id=c["claim_id"], text=c["text"],
                   category=c["category"], start_seconds=c["start_seconds"], end_seconds=c["end_seconds"],
                   source_segment_ids=[], requires_verification=True, claim_kind=c["claim_kind"],
                   label=c["label"], deciding=c["deciding"], search_trail=c.get("search_trail"))
    row.stance = ClaimStanceRow(stance=c["stances"][0]["stance"], segment_ids=[],
                                rationale=c["stances"][0]["rationale"])
    row.verification = VerificationResultRow(verdict=c["verdict"], explanation=c["explanation"],
                                             limitations=list(c["limitations"]),
                                             retrieval_attempts=c["retrieval_attempts"])
    for e in c["evidence"]:
        ev = EvidenceRecordRow(job_id="d2bf4179", evidence_id=f"ev_{e['pmid']}", source=e["source"], pmid=e["pmid"],
                               doi=e.get("doi"), title=e["title"], abstract="",
                               publication_type=list(e.get("publication_type") or []),
                               publication_year=e.get("year"), study_type=e.get("study_type"))
        row.evidence_links.append(ClaimEvidenceRow(evidence=ev, relation=e["relation"],
                                                   relevance_score=e.get("relevance"), rank=e.get("rank")))
    return row


def index(job: dict) -> dict:
    return {s["segment_id"]: rv.SegmentView(segment_id=s["segment_id"], source="speech",
                                            start_seconds=s["start_seconds"], end_seconds=s["end_seconds"],
                                            text=s["text"])
            for s in job["transcript_segments"]}


# ============================================================== (a) evidence ids


def test_real_c7_explanation_carries_ids_and_the_view_renders_them_as_titles(job):
    c7 = claim(job, "c7")
    assert has_evidence_ids(c7["explanation"])  # the production text
    view = rv.claim_view(claim_row(c7, job), index(job))
    assert not has_evidence_ids(view.verdict_explanation)
    assert not any(has_evidence_ids(x) for x in view.limitations)
    by_pmid = {e["pmid"]: e["title"] for e in c7["evidence"]}
    assert f"“{short_title(by_pmid['37337123'])}”" in view.verdict_explanation
    assert view.verdict_explanation.startswith("Several reviews describe vitamin K as an essential cofactor")


def test_render_ids_uses_short_title_else_pmid_and_drops_unknown_ids():
    names = {"ev_1": source_name("Vitamin K prophylaxis for prevention of vitamin K deficiency bleeding: "
                                 "a systematic review."),
             "ev_2": source_name("", "222")}
    out = render_evidence_ids("Reviews agree (ev_1, ev_2, ev_9).", names)
    assert out == "Reviews agree (“Vitamin K prophylaxis for prevention of vitamin K…”; PMID 222)."
    assert render_evidence_ids("One paper (ev_9) says so.", names) == "One paper says so."
    assert render_evidence_ids("No ids here.", names) == "No ids here."


def test_verifier_repairs_once_when_the_answer_names_evidence_ids(job):
    c7 = claim(job, "c7")
    clean = {**stored_answer(c7), "explanation": "Several reviews describe vitamin K as an essential cofactor."}
    caller = Scripted(stored_answer(c7), clean)
    result, errors = vf.verify_claim(graph_claim(c7), records(c7), caller, "system", "verify_v3")
    assert len(caller.prompts) == 2
    assert "internal evidence IDs" in caller.prompts[1] and "ev_37337123" in caller.prompts[1]
    assert any("evidence_id_in_text" in e.message for e in errors)
    assert not any(e.message.startswith("guardrail:") for e in errors)
    assert result.verdict == Verdict.SUPPORTED
    assert result.explanation == clean["explanation"]
    assert set(result.supporting_evidence_ids) == set(stored_answer(c7)["supporting_evidence_ids"])


def test_verifier_renders_ids_when_the_repair_still_names_them(job):
    c7 = claim(job, "c7")
    caller = Scripted(stored_answer(c7))  # same answer twice
    result, _ = vf.verify_claim(graph_claim(c7), records(c7), caller, "system", "verify_v3")
    assert len(caller.prompts) == 2
    assert not has_evidence_ids(result.explanation)
    assert "“" in result.explanation
    assert result.verdict == Verdict.SUPPORTED  # the verdict and citations are kept


def test_verifier_prompt_tells_the_model_not_to_write_ids(job):
    c7 = claim(job, "c7")
    prompt = vf.build_prompt(graph_claim(c7), records(c7), "system")
    assert "never write an evidence ID (ev_...)" in prompt.render()


# ============================================================== (b) "the reviewer"


def test_real_reviewer_limitations_are_reworded(job):
    texts = [x for cid in ("c11", "c14") for x in claim(job, cid)["limitations"] if mentions_reviewer(x)]
    assert len(texts) == 2  # the production rows
    out = [reword_reviewer(x) for x in texts]
    assert out[0].startswith("A second automated check was right that the evidence focuses")
    assert out[1].startswith("A second automated check is right that these gaps")
    assert not any(mentions_reviewer(x) for x in out)
    view = rv.claim_view(claim_row(claim(job, "c14"), job), index(job))
    assert not any(mentions_reviewer(x) for x in view.limitations)


@pytest.mark.parametrize("text,want", [
    ("As the reviewer noted, the trials are small.", "As a second automated check noted, the trials are small."),
    ("The reviewer's point stands.", "A second automated check's point stands."),
    ("a reviewer flagged it", "a second automated check flagged it"),
    ("Peer-reviewed trials", "Peer-reviewed trials"),
])
def test_reword_reviewer(text, want):
    assert reword_reviewer(text) == want


def test_critic_notes_are_not_called_reviewer_notes(job):
    c14 = claim(job, "c14")
    critic = CriticResult(claim_id="c14", decision=CriticDecision.REVISE_VERIFICATION,
                          issues=["'overwhelming' is strong for observational data"])
    text = vf.build_prompt(graph_claim(c14), records(c14), "system", critic=critic).render()
    assert "REVIEWER NOTES" not in text
    assert "NOTES FROM A SECOND AUTOMATED CHECK" in text and "never 'the reviewer'" in text


def test_verifier_output_reviewer_wording_is_rewritten(job):
    c14 = claim(job, "c14")
    answer = stored_answer(c14)
    assert any(mentions_reviewer(x) for x in answer["limitations"])
    result, _ = vf.verify_claim(graph_claim(c14), records(c14), Scripted(answer), "system", "verify_v3")
    assert not any(mentions_reviewer(x) for x in [result.explanation, *result.limitations])


# ============================================================== (c) one study type


def test_real_c7_counts_agree_with_the_listed_types(job):
    view = rv.claim_view(claim_row(claim(job, "c7"), job), index(job))
    counts = {(x.study_type, x.relation): x.count for x in view.study_type_counts}
    assert counts == {("narrative_review", "SUPPORTS"): 4, ("case_report", "SUPPORTS"): 2}
    listed: dict = {}
    for e in view.evidence:
        listed[(e.study_type, e.relation)] = listed.get((e.study_type, e.relation), 0) + 1
    assert listed == counts  # the same field, counted
    assert sum(counts.values()) == len(view.evidence) == 6


def test_every_real_claim_counts_from_the_listed_type(job):
    for c in job["claims"]:
        view = rv.claim_view(claim_row(c, job), index(job))
        total = sum(x.count for x in view.study_type_counts)
        assert total == len([e for e in view.evidence if e.relation in ("SUPPORTS", "CONTRADICTS")])
        assert all(e.study_type for e in view.evidence)


def test_row_without_a_study_type_gets_the_classifier_type():
    row = EvidenceRecordRow(evidence_id="ev_1", source="pubmed", title="A trial", abstract="",
                            publication_type=["Randomized Controlled Trial"], study_type=None)
    assert rv.study_type_of(row) == "rct"
    bare = EvidenceRecordRow(evidence_id="ev_2", source="pubmed", title="Notes", abstract="",
                             publication_type=[], study_type=None)
    assert rv.study_type_of(bare) == "unknown"


# ============================================================== (d) titles


def test_real_titles_lose_the_trailing_full_stop(job):
    titles = [e["title"] for c in job["claims"] for e in c["evidence"]]
    assert any(t.endswith(".") for t in titles)  # what PubMed sends
    for t in titles:
        assert not clean_title(t).endswith(".") or clean_title(t).endswith("...")
        assert ".." not in source_line(t, year=2016).replace("...", "")
    c1 = claim(job, "c1")
    view = rv.claim_view(claim_row(c1, job), index(job))
    assert view.evidence[0].title == ("Vitamin K prophylaxis for prevention of vitamin K deficiency bleeding: "
                                      "a systematic review")


@pytest.mark.parametrize("title,line", [
    ("A systematic review.", "A systematic review. JAMA, 2016."),
    ("A systematic review..", "A systematic review. JAMA, 2016."),
    ("Is it safe?", "Is it safe? JAMA, 2016."),
])
def test_source_line_has_one_full_stop_after_the_title(title, line):
    assert source_line(title, journal="JAMA", year=2016) == line


# ============================================================== (e) speaker quote


def _segments(job: dict) -> list[QuoteSegment]:
    return [QuoteSegment(s["segment_id"], s["start_seconds"], s["end_seconds"], s["text"])
            for s in job["transcript_segments"]]


def test_real_quotes_carry_the_claim_not_the_first_segment(job):
    segs = _segments(job)

    def quote(cid: str) -> str:
        c = claim(job, cid)
        q = best_overlap_quote(c["text"], segs, c["start_seconds"], c["end_seconds"])
        assert q is not None
        return q.text

    # c2 "a JAMA study published November 5th examined more than 5.2 million infants":
    # the first segment of its span was "latest research is very concerning. The new study".
    assert "JAMA" in quote("c2") and "5.2 million infants" in quote("c2")
    # c3: the first segment was the tail of c2 ("infants in the United States. ...").
    assert quote("c3").startswith("percentage of newborns not receiving vitamin K more than doubled")
    assert "6.8% in 2025" in quote("c3")
    assert "47% higher risk of bleeding" in quote("c4")
    # c9: the first segment was the end of c8 ("bleeding, sometimes without any warning").
    assert "bleeding in the brain can cause permanent neurological damage or death" in quote("c9")
    assert quote("c7") == "levels of vitamin K, which is essential for blood clotting."  # one segment suffices


def test_view_exposes_speaker_quote(job):
    view = rv.claim_view(claim_row(claim(job, "c2"), job), index(job))
    assert view.speaker_quote and "JAMA" in view.speaker_quote
    assert "t5" in view.speaker_quote_segment_ids  # "published November 5th in JAMA examined …"


def test_no_quote_when_nothing_in_the_span_says_the_claim():
    segs = [QuoteSegment("t1", 0, 2, "hello and welcome back")]
    assert best_overlap_quote("vitamin K prevents bleeding", segs, 0, 2) is None


# ============================================================== (f) journal and date


def test_efetch_gives_journal_abbreviation_and_date():
    art = jama_article()
    assert (art.pmid, art.journal_abbrev, art.pub_date) == ("42986716", "JAMA", "2026-11-05")
    rec = to_evidence(art, "q")
    assert (rec.journal, rec.pub_date) == ("JAMA", "2026-11-05")
    # the record cache round-trips, and entries cached before T65 still load
    assert PubMedArticle.from_json(art.to_json()) == art
    old = {k: v for k, v in art.to_json().items() if k not in ("journal_abbrev", "pub_date")}
    assert PubMedArticle.from_json(old).pub_date is None


@pytest.mark.parametrize("pubdate,want", [
    ("<Year>2016</Year>", "2016"),
    ("<Year>2016</Year><Month>Nov</Month>", "2016-11"),
    ("<Year>2016</Year><Month>3</Month><Day>7</Day>", "2016-03-07"),
    ("<MedlineDate>2016 Nov-Dec</MedlineDate>", "2016-11"),
    ("<MedlineDate>Winter 2016</MedlineDate>", None),
])
def test_pub_date_precision(pubdate, want):
    xml = ("<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><Journal>"
           f"<JournalIssue><PubDate>{pubdate}</PubDate></JournalIssue><Title>Journal</Title>"
           "</Journal><ArticleTitle>T.</ArticleTitle></Article><MedlineJournalInfo><MedlineTA>J TA</MedlineTA>"
           "</MedlineJournalInfo></MedlineCitation></PubmedArticle></PubmedArticleSet>")
    art = parse_efetch(xml)[0]
    assert art.pub_date == want
    assert art.journal_abbrev == "J TA"  # MedlineTA when there is no ISOAbbreviation


def test_verifier_sees_journal_and_date(job):
    c2 = claim(job, "c2")
    art = jama_article()
    index_text = vf.evidence_index([to_evidence(art, "q")])
    assert "journal: JAMA" in index_text and "published: 2026-11-05" in index_text
    assert "a JAMA study published November 5th" in c2["text"]


def test_api_exposes_journal_and_pub_date_from_the_stored_trail(job):
    c2 = claim(job, "c2")
    art = jama_article()
    rec = to_evidence(art, "q")
    row = claim_row(c2, job)
    row.search_trail = _with_source_meta(dict(c2["search_trail"]), [rec])
    view = rv.claim_view(row, index(job))
    jama = next(e for e in view.evidence if e.pmid == "42986716")
    assert (jama.journal, jama.pub_date) == ("JAMA", "2026-11-05")
    assert view.search_trail is not None  # the extra key does not break the trail view


def test_rows_stored_before_t65_fall_back_to_the_year(job):
    view = rv.claim_view(claim_row(claim(job, "c2"), job), index(job))
    e = view.evidence[0]
    assert e.journal is None and e.pub_date == str(claim(job, "c2")["evidence"][0]["year"])
