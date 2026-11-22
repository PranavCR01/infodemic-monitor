"""Reranker (T05, issue #32, design §6 "Reranking: keep what tests the claim").

Acceptance criteria covered here:

- at most 10 papers per claim, each with a relevance score;
- study type recorded per paper, scored separately from relevance;
- hand-labelled relevance check on at least 10 claims, precision@5 reported;
- comparison against PubMed's unranked order on the same claims.

No network, no models.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app.core.graph import routing as r
from app.core.graph.builder import compile_graph, run_config
from app.core.graph.checkpoint import memory_checkpointer
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.retrieval_nodes import make_rerank_node, make_retrieval_nodes
from app.core.graph.state import GraphClaim, assert_checkpoint_safe, initial_state
from app.core.retrieval import EvidenceRecord
from app.core.retrieval.rerank import (
    MAX_EVIDENCE_PER_CLAIM,
    QUALITY,
    EvidenceClass,
    RerankConfig,
    Reranker,
    StudyType,
    classify_study,
    evidence_class,
    rerank_evidence,
)
from app.core.retrieval.retriever import EvidenceRetriever
from app.evaluation.metrics import precision_at_k
from app.evaluation.rerank_eval import RELEVANCE_SET, evaluate, format_report, load_relevance_set, main
from app.tests.pubmed_fixtures import RecordedPubMed

LEMON = "Lemon water cures cancer."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def rec(n: int | str, title: str, abstract: str = "", types=("Journal Article",), source="pubmed", **kw):
    n = str(n)
    if source == "library":
        return EvidenceRecord(evidence_id=f"lib_{n}_p1", source="library", document_id=n, page=1,
                              title=title, abstract=abstract, publication_type=list(types), **kw)
    return EvidenceRecord(evidence_id=f"ev_{n}", source="pubmed", pmid=n, title=title,
                          abstract=abstract, publication_type=list(types),
                          source_url=f"https://pubmed.ncbi.nlm.nih.gov/{n}/", **kw)


# ------------------------------------------------------------------ study type


@pytest.mark.parametrize(
    "types, expected",
    [
        (["Journal Article", "Systematic Review"], StudyType.SYSTEMATIC_REVIEW),
        (["Meta-Analysis"], StudyType.SYSTEMATIC_REVIEW),
        (["Journal Article", "Randomized Controlled Trial"], StudyType.RCT),
        (["Practice Guideline"], StudyType.GUIDELINE),
        (["Clinical Trial, Phase II"], StudyType.CLINICAL_TRIAL),
        (["Observational Study"], StudyType.OBSERVATIONAL),
        (["Case Reports"], StudyType.CASE_REPORT),
        (["Review"], StudyType.NARRATIVE_REVIEW),
        (["Editorial"], StudyType.OPINION),
        (["Randomized Controlled Trial, Veterinary"], StudyType.ANIMAL),
    ],
)
def test_study_type_is_a_lookup_on_publication_type(types, expected):
    assert classify_study(rec(1, "A paper", "Synthetic.", types)) == expected


@pytest.mark.parametrize(
    "title, abstract, expected",
    [
        ("Lemon extract and breast cancer cells", "Viability of MCF-7 cell lines in vitro.", StudyType.IN_VITRO),
        ("Garlic and colds in mice", "Mice were fed garlic.", StudyType.ANIMAL),
        ("Coffee and diabetes", "A prospective cohort of 40,000 adults.", StudyType.OBSERVATIONAL),
        ("Garlic and colds", "Participants were randomized to garlic or placebo.", StudyType.RCT),
        ("Zinc for colds: a systematic review", "", StudyType.SYSTEMATIC_REVIEW),
        ("Phenolic content of lemon juice", "Composition by HPLC.", StudyType.OTHER),
        ("Something", "", StudyType.OTHER),
    ],
)
def test_untyped_pubmed_records_fall_back_to_fixed_cues(title, abstract, expected):
    assert classify_study(rec(1, title, abstract)) == expected


def test_tagged_human_trial_is_not_demoted_by_animal_words():
    r1 = rec(1, "Garlic and colds", "Earlier work in mice suggested benefit; adults were randomised.",
             ["Randomized Controlled Trial"])
    assert classify_study(r1) == StudyType.RCT


def test_record_with_no_type_at_all_is_unknown_and_ranks_below_every_tagged_type():
    assert classify_study(rec(1, "Something", "", types=())) == StudyType.UNKNOWN
    assert QUALITY[StudyType.UNKNOWN] < min(v for k, v in QUALITY.items() if k != StudyType.UNKNOWN)


def test_library_records_keep_the_uploaders_type_and_never_guess():
    assert classify_study(rec("d1", "Garlic trial", "randomised adults", ["Unknown"], source="library")) == StudyType.UNKNOWN
    assert classify_study(rec("d1", "x", "", ["Randomized Controlled Trial"], source="library")) == StudyType.RCT
    assert classify_study(rec("d1", "x", "", ["animal"], source="library")) == StudyType.ANIMAL


def test_quality_order_follows_the_design():
    q = QUALITY
    assert q[StudyType.SYSTEMATIC_REVIEW] >= q[StudyType.RCT] > q[StudyType.OBSERVATIONAL]
    assert q[StudyType.OBSERVATIONAL] > max(q[StudyType.ANIMAL], q[StudyType.IN_VITRO], q[StudyType.CASE_REPORT])


def test_human_clinical_evidence_is_distinguished_from_mechanistic_animal_and_general():
    assert evidence_class(StudyType.RCT) == EvidenceClass.HUMAN_CLINICAL
    assert evidence_class("observational") == EvidenceClass.HUMAN_OBSERVATIONAL
    assert evidence_class(StudyType.IN_VITRO) == EvidenceClass.MECHANISTIC
    assert evidence_class(StudyType.ANIMAL) == EvidenceClass.ANIMAL
    assert evidence_class(StudyType.OTHER) == EvidenceClass.GENERAL
    assert set(evidence_class(s) for s in StudyType)  # every type maps


# ------------------------------------------------------------------- relevance


def scores(claim, records, **cfg):
    res = Reranker(RerankConfig(**cfg) if cfg else RerankConfig()).rerank(claim, records)
    return {s.record.evidence_id: s.relevance for s in res.scored}, res


def test_lemon_cell_study_is_less_relevant_than_a_human_trial():
    cell = rec(1, "Lemon peel extract induces apoptosis in breast cancer cells", "Cell lines in vitro.")
    trial = rec(2, "Lemon water and survival in patients with cancer: a randomised trial", "",
                ["Randomized Controlled Trial"])
    s, res = scores(LEMON, [cell, trial])
    assert s["ev_2"] > s["ev_1"]
    assert [r.evidence_id for r in res.kept][0] == "ev_2"
    assert res.kept[0].study_type == "rct"


def test_a_paper_on_only_one_side_of_the_claim_scores_zero():
    only_lemon = rec(1, "Lemon juice and kidney stones: a randomised trial", "Lemon lemon lemon.",
                     ["Randomized Controlled Trial"])
    only_cancer = rec(2, "Chemotherapy outcomes in cancer: a cohort", "", ["Observational Study"])
    s, res = scores(LEMON, [only_lemon, only_cancer])
    assert s == {"ev_1": 0.0, "ev_2": 0.0}
    assert res.kept == [] and not res.cleared_threshold
    assert set(res.dropped_below_threshold) == {"ev_1", "ev_2"}


def test_title_hits_beat_abstract_hits():
    title = rec(1, "Garlic and the common cold", "")
    abstract = rec(2, "A supplement study", "Garlic was given to adults and colds were counted.")
    s, _ = scores("Garlic stops colds.", [abstract, title])
    assert s["ev_1"] == 1.0 and s["ev_2"] == pytest.approx(0.7)


def test_claim_population_missing_from_paper_lowers_relevance():
    kids = rec(1, "Vaccines and autism in children", "")
    adults = rec(2, "Vaccines and autism", "")
    s, _ = scores("Vaccines cause autism in children.", [kids, adults])
    assert s["ev_1"] == 1.0 and s["ev_2"] == pytest.approx(0.8)


def test_misinformation_studies_are_not_evidence_for_the_claim():
    about = rec(1, "5G and COVID-19 misinformation on Twitter", "Content analysis of tweets.")
    test = rec(2, "5G coverage and COVID-19 incidence: an ecological study", "", ["Observational Study"])
    s, _ = scores("5G spreads coronavirus.", [about, test])
    assert s["ev_2"] == 1.0 and s["ev_1"] == pytest.approx(0.5)


def test_outcome_unknown_to_the_lexicon_still_has_to_match():
    # "cough" is not in the MeSH lexicon: the leftover word stands in for the outcome.
    on = rec(1, "Honey for cough in children: a randomised trial", "", ["Randomized Controlled Trial"])
    off = rec(2, "Honey dressings for burns in children: a randomised trial", "", ["Randomized Controlled Trial"])
    s, res = scores("Honey cures cough in children.", [off, on])
    assert s["ev_1"] == 1.0 and s["ev_2"] == 0.0
    assert [r.evidence_id for r in res.kept] == ["ev_1"]


def test_claim_without_any_concept_uses_keyword_overlap():
    r1 = rec(1, "Bananas and skin health", "")
    r2 = rec(2, "Unrelated topic", "")
    s, _ = scores("Bananas are amazing for your skin", [r1, r2])
    assert s["ev_1"] > 0.5 and s["ev_2"] == 0.0


# --------------------------------------------------------------- ranking & cap


def many_relevant(n):
    return [rec(1000 + i, f"Garlic and the common cold, study {i}", "", ["Observational Study"]) for i in range(n)]


def test_at_most_ten_papers_per_claim_each_with_scores_and_study_type():
    res = Reranker().rerank("Garlic stops colds.", many_relevant(15))
    assert len(res.kept) == MAX_EVIDENCE_PER_CLAIM
    assert len(res.dropped_over_cap) == 5
    for e in res.kept:
        assert e.relevance_score is not None and 0.0 <= e.relevance_score <= 1.0
        assert e.study_type == "observational" and e.quality_score == QUALITY[StudyType.OBSERVATIONAL]


def test_ties_keep_pubmed_order_and_reranking_is_deterministic():
    recs = many_relevant(12)
    a = Reranker().rerank("Garlic stops colds.", recs)
    b = Reranker().rerank("Garlic stops colds.", list(recs))
    assert [e.evidence_id for e in a.kept] == [e.evidence_id for e in b.kept]
    assert [e.evidence_id for e in a.kept] == [e.evidence_id for e in recs[:10]]


def test_study_type_breaks_near_ties_but_relevance_dominates():
    obs = rec(1, "Garlic and the common cold", "", ["Observational Study"])
    sr = rec(2, "Garlic and the common cold: a systematic review", "", ["Systematic Review"])
    off_topic_sr = rec(3, "Garlic and blood pressure: a systematic review", "", ["Systematic Review"])
    res = Reranker().rerank("Garlic stops colds.", [obs, sr, off_topic_sr])
    assert [e.evidence_id for e in res.kept] == ["ev_2", "ev_1"]
    # Relevance and quality stay separate fields.
    assert res.kept[0].relevance_score == res.kept[1].relevance_score == 1.0
    assert res.kept[0].quality_score > res.kept[1].quality_score


def test_reranking_keeps_every_identifier_from_the_input():
    r1 = rec(1, "Garlic and the common cold", "", ["Systematic Review"], doi="10.9999/x", query="q")
    out = Reranker().rerank("Garlic stops colds.", [r1]).kept[0]
    for f in ("evidence_id", "pmid", "doi", "title", "abstract", "source_url", "query", "publication_type"):
        assert getattr(out, f) == getattr(r1, f)
    assert r1.relevance_score is None  # input untouched (records are immutable)


def test_injected_relevance_model_replaces_the_lexical_scorer():
    seen = {}

    def model(claim, records):
        seen["claim"] = claim
        return [0.1, 0.9, 1.7]

    recs = [rec(1, "a"), rec(2, "b"), rec(3, "c")]
    res = Reranker(relevance_model=model).rerank("Garlic stops colds.", recs)
    assert seen["claim"] == "Garlic stops colds."
    assert [e.evidence_id for e in res.kept] == ["ev_3", "ev_2"]
    assert res.kept[0].relevance_score == 1.0  # clamped
    with pytest.raises(ValueError):
        Reranker(relevance_model=lambda c, rs: [0.5]).rerank("x", recs)


def test_functional_form_for_the_mcp_tool_caps_k_at_ten():
    assert len(rerank_evidence("Garlic stops colds.", many_relevant(15), k=3)) == 3
    assert len(rerank_evidence("Garlic stops colds.", many_relevant(15), k=50)) == 10


def test_records_without_the_new_fields_still_load():
    old = {"evidence_id": "ev_1", "source": "pubmed", "title": "t", "relevance_score": None}
    assert EvidenceRecord.model_validate(old).study_type is None


# ------------------------------------------------------------------------ node


def claim(cid, text):
    return GraphClaim(claim_id=cid, claim_text=text, claim_category="treatment_efficacy",
                      source_segment_ids=["t1"], start_seconds=0.0, end_seconds=1.0)


def test_rerank_node_writes_only_reranked_evidence_capped_and_scored():
    node = make_rerank_node()[r.RERANK_EVIDENCE]
    state = {
        "claims": [claim("c1", "Garlic stops colds."), claim("c2", LEMON)],
        "retrieved_evidence": {
            "c1": many_relevant(14),
            "c2": [rec(9, "Lemon peel extract and breast cancer cells", "In vitro cell lines.")],
        },
    }
    out = node(state)
    assert set(out) == {"reranked_evidence"}
    assert len(out["reranked_evidence"]["c1"]) == 10
    assert all(e.relevance_score is not None and e.study_type for e in out["reranked_evidence"]["c1"])
    kept_c2 = out["reranked_evidence"]["c2"]
    assert [e.study_type for e in kept_c2] == ["in_vitro"]  # kept, but marked mechanistic
    assert_checkpoint_safe(out)


def test_rerank_node_failure_is_recorded_and_falls_back_to_pubmed_order():
    def broken(claim_text, records):
        raise RuntimeError("model down")

    node = make_rerank_node(Reranker(relevance_model=broken))[r.RERANK_EVIDENCE]
    recs = many_relevant(12)
    out = node({"claims": [claim("c1", "Garlic stops colds.")], "retrieved_evidence": {"c1": recs}})
    assert out["reranked_evidence"]["c1"] == recs[:10]
    assert out["errors"][0].node == r.RERANK_EVIDENCE and out["errors"][0].claim_id == "c1"


def test_real_rerank_node_in_the_graph_on_recorded_pubmed():
    server = RecordedPubMed()
    nodes = make_stub_nodes()
    nodes.update(make_retrieval_nodes(EvidenceRetriever(server.client())))
    graph = compile_graph(nodes, checkpointer=memory_checkpointer())
    state = initial_state(job_id="job-t05", video_id="vid-1", media_uri="videos/vid-1/video.mp4",
                          pipeline_version="t05-test")
    out = graph.invoke(state, run_config("job-t05"))
    assert server.unknown_queries == []
    for cid, recs in out["reranked_evidence"].items():
        assert len(recs) <= MAX_EVIDENCE_PER_CLAIM
        retrieved = {e.evidence_id for e in out["retrieved_evidence"][cid]}
        for e in recs:
            assert e.evidence_id in retrieved  # reranking never invents a paper
            assert e.relevance_score >= RerankConfig().min_relevance and e.study_type
    garlic = out["reranked_evidence"]["c2"]
    assert garlic and garlic[0].study_type == "systematic_review"
    assert out["errors"] == []


# ------------------------------------------------------------ relevance check


def test_precision_at_k_counts_empty_slots_as_misses():
    assert precision_at_k({"a", "b"}, ["a", "x", "b", "y", "z"], 5) == 0.4
    assert precision_at_k({"a"}, ["a"], 5) == 0.2
    assert precision_at_k({"a"}, [], 5) == 0.0


def test_relevance_set_has_at_least_ten_hand_labelled_claims():
    claims = load_relevance_set()
    assert len(claims) >= 10
    for papers in claims.values():
        assert len(papers) >= 5
        assert any(p.label == 2 for p in papers)
        assert [p.pubmed_rank for p in papers] == list(range(1, len(papers) + 1))
        assert all(p.label in (0, 1, 2) for p in papers)
        assert all(p.abstract.startswith("Synthetic.") and p.pmid.startswith("98") for p in papers)


def test_reranker_beats_pubmed_order_on_precision_at_5():
    report = evaluate()
    s = report["summary"]
    assert report["claims"] >= 10
    assert s["reranked"]["precision_at_5"] > s["pubmed"]["precision_at_5"]
    assert s["reranked"]["ndcg_at_10"] > s["pubmed"]["ndcg_at_10"]
    assert s["reranked"]["off_topic_kept"] < s["pubmed"]["off_topic_kept"]
    assert s["reranked"]["precision_at_5"] <= s["ceiling_precision_at_5"]
    for c in report["per_claim"]:
        assert len(c["reranked_ids"]) <= MAX_EVIDENCE_PER_CLAIM
        assert all(c["study_types"].values())
    text = format_report(report)
    assert "precision_at_5" in text and "PubMed order" in text


def test_relevance_set_matches_its_builder():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "build_rerank_relevance_set.py"
    spec = importlib.util.spec_from_file_location("build_rerank_relevance_set", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    on_disk = [json.loads(line) for line in RELEVANCE_SET.read_text().splitlines() if line.strip()]
    assert on_disk == mod.rows()


def test_cli_prints_report_and_writes_json(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--out", str(out)]) == 0
    assert "Reranker relevance check" in capsys.readouterr().out
    assert json.loads(out.read_text())["claims"] >= 10
