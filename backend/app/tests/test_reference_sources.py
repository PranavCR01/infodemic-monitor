"""T17: authoritative reference sources for facts of record, plus ``claim_kind``
(design §4, §6 "Trusted sources beyond PubMed").

No network: publisher pages and NCBI Bookshelf come from synthetic fixtures
(``fixtures/references``) through ``httpx.MockTransport``; models are scripted.
"""
from __future__ import annotations

import hashlib
import re
import socket
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.core.graph import claims as cl
from app.core.graph import routing as r
from app.core.graph.judge import Decision, InvalidExplanation, check_explanation
from app.core.graph.retrieval_nodes import make_retrieval_nodes
from app.core.graph.state import FusedSegment, GraphClaim, TranscriptSegment
from app.core.graph.verifier import evidence_index, load_prompt
from app.core.inference.providers import graph_provider as gp
from app.core.retrieval.claim_kind import infer_claim_kind, resolve_claim_kind
from app.core.retrieval.references import (
    InMemorySnapshotStore,
    ReferenceFetchError,
    SnapshotMismatch,
    StoredSnapshots,
    best_passage,
    html_to_text,
    is_reference_evidence_id,
    load_reference_config,
    match_catalogue,
    parse_book_chapters,
    reference_evidence_id,
    text_sha256,
    url_allowed,
)
from app.core.retrieval.references.config import ReferenceConfig
from app.core.retrieval.references.fetcher import FetchedPage
from app.core.retrieval.rerank import EvidenceClass, Reranker, StudyType, classify_study, evidence_class
from app.core.retrieval.retriever import EvidenceRetriever
from app.core.retrieval.schemas import EvidenceRecord
from app.core.schemas.pipeline import MisinfoLabel
from app.tests.pubmed_fixtures import RecordedPubMed
from app.tests.reference_fixtures import EUTILS, STORED_AT, RecordedReferences, build_stored_archive
from app.tests.test_graph_integration import BACKEND, FakeSingleCall, ScriptedClient, _db, _job, default_script, make_router

MMR = "Children only need one dose of the MMR vaccine, at 10 years old."
SCHEDULE_URL = "https://www.cdc.gov/vaccines/hcp/imz-schedules/child-adolescent-age.html"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def cfg() -> ReferenceConfig:
    return load_reference_config()


# ================================================================ allow-list config


def test_config_loads_and_covers_the_doc_table(cfg):
    ids = {s.id for s in cfg.sources}
    # §6 table: Bookshelf, CDC/WHO schedules, FDA/EMA/EFSA, WHO/CDC/NHS/ECDC, GHO, USDA.
    assert {"ncbi_bookshelf", "cdc", "who", "fda", "ema", "efsa", "nhs", "ecdc", "usda_fooddata"} <= ids
    assert next(s for s in cfg.sources if s.id == "ncbi_bookshelf").backend == "bookshelf"
    for page in cfg.catalogue:  # every catalogue URL is inside its own source's allow-list
        assert url_allowed(page.url, cfg.source(page.source)), page.id


@pytest.mark.parametrize("bad", [
    {"url": "http://www.cdc.gov/x"},                         # not HTTPS
    {"url": "https://evil.example/x"},                       # host not on the list
    {"url": "https://www.cdc.gov.evil.example/x"},           # suffix trick
    {"source": "nowhere"},                                   # unknown source
])
def test_config_rejects_catalogue_pages_outside_the_allow_list(bad):
    page = {"id": "p", "source": "cdc", "title": "t", "url": "https://www.cdc.gov/x", "keywords": ["k"], **bad}
    src = {"id": "cdc", "name": "CDC", "publisher": "CDC", "backend": "catalogue", "allowed_hosts": ["www.cdc.gov"]}
    with pytest.raises(ValueError):
        ReferenceConfig.model_validate({"version": "t", "sources": [src], "catalogue": [page]})


def test_config_rejects_wildcard_hosts():
    src = {"id": "x", "name": "X", "publisher": "X", "backend": "catalogue", "allowed_hosts": ["*.gov"]}
    with pytest.raises(ValueError):
        ReferenceConfig.model_validate({"version": "t", "sources": [src]})


@pytest.mark.parametrize("url,ok", [
    ("https://www.who.int/news-room/fact-sheets/detail/measles", True),
    ("https://www.who.int/some/other/path", False),          # outside WHO's path prefixes
    ("https://www.who.int/news-room/fact-sheets/../../admin", False),
    ("https://user:pw@www.who.int/news-room/fact-sheets/x", False),
    ("https://www.who.int:8443/news-room/fact-sheets/x", False),
    ("http://www.who.int/news-room/fact-sheets/x", False),
    ("https://who.int/news-room/fact-sheets/x", False),      # exact host only
])
def test_url_allowed(cfg, url, ok):
    assert url_allowed(url, cfg.source("who")) is ok


# ======================================================================= fetcher


def test_fetcher_refuses_urls_off_the_allow_list_without_a_request(cfg):
    rec = RecordedReferences()
    with pytest.raises(ReferenceFetchError) as e:
        rec.fetcher(cfg).fetch("https://evil.example/page", cfg.source("cdc"))
    assert e.value.kind == "not_allowed" and rec.requests == []


def test_fetcher_does_not_follow_redirects(cfg):
    rec = RecordedReferences()
    rec.overrides[SCHEDULE_URL] = lambda req: httpx.Response(302, headers={"location": "https://evil.example/"},
                                                             request=req)
    with pytest.raises(ReferenceFetchError) as e:
        rec.fetcher(cfg).fetch(SCHEDULE_URL, cfg.source("cdc"))
    assert e.value.kind == "http" and len(rec.requests) == 1


def _serve_fixture(rec: RecordedReferences, url: str, name: str) -> None:
    """Serve a fixture page at ``url`` (the fake www.cdc.gov otherwise answers 403)."""
    html = (BACKEND / "app/tests/fixtures/references" / name).read_text()
    rec.overrides[url] = lambda req: httpx.Response(200, text=html, request=req,
                                                    headers={"content-type": "text/html"})


def test_fetcher_caps_body_and_checks_content_type(cfg):
    small = cfg.model_copy(update={"max_response_bytes": 100})
    rec = RecordedReferences()
    _serve_fixture(rec, SCHEDULE_URL, "cdc_child_schedule.html")
    with pytest.raises(ReferenceFetchError) as e:
        rec.fetcher(small).fetch(SCHEDULE_URL, small.source("cdc"))
    assert e.value.kind == "too_large"
    rec.overrides[SCHEDULE_URL] = lambda req: httpx.Response(200, content=b"%PDF", request=req,
                                                             headers={"content-type": "application/pdf"})
    with pytest.raises(ReferenceFetchError) as e:
        rec.fetcher(cfg).fetch(SCHEDULE_URL, cfg.source("cdc"))
    assert e.value.kind == "content_type"


def test_html_to_text_drops_scripts_navigation_and_footer():
    title, text = html_to_text(
        "<html><head><title>T</title><script>evil()</script></head><body><nav>menu</nav>"
        "<p>First <b>para</b>.</p><p>Second</p><footer>foot</footer></body></html>")
    assert title == "T"
    assert text == "First para.\n\nSecond"


def test_fetched_page_hash_is_of_the_text(cfg):
    rec = RecordedReferences()
    _serve_fixture(rec, SCHEDULE_URL, "cdc_child_schedule.html")
    page = rec.fetcher(cfg).fetch(SCHEDULE_URL, cfg.source("cdc"))
    assert page.sha256 == hashlib.sha256(page.text.encode()).hexdigest()
    assert "ignore me" not in page.text and "menu" not in page.text  # script and nav dropped
    assert page.retrieved_at == "2026-11-22T12:00:00+00:00"


# ====================================================================== passages


def test_best_passage_quotes_the_page_and_needs_overlap():
    text = "Opening words about the site.\n\nChildren need two doses of MMR vaccine at 12 months.\n\nFooter."
    p = best_passage("The MMR vaccine is given at 12 months", text)
    assert p is not None and p.text == "Children need two doses of MMR vaccine at 12 months."
    assert best_passage("Garlic prevents colds", text) is None


def test_long_paragraphs_are_cut_to_the_limit():
    long = " ".join(f"Sentence {i} about the MMR vaccine schedule." for i in range(100))
    p = best_passage("MMR vaccine schedule", long, max_chars=300)
    assert p is not None and len(p.text) <= 300 and p.text in long


# ======================================================================== search


def test_catalogue_matching_by_keyword(cfg):
    ids = [p.id for p, _ in match_catalogue(MMR, cfg)]
    assert ids[0] in ("cdc_child_schedule", "cdc_measles_vaccine")
    assert "who_salt" not in ids
    assert match_catalogue("Drinking hot water cures the flu", cfg) == []


def test_reference_records_are_cited_like_papers(cfg):
    rec = RecordedReferences(books=False)
    snaps = InMemorySnapshotStore()
    found = rec.searcher(cfg, snapshots=snaps).search(MMR)
    # The NHS page has no fixture (404): recorded, and the other pages still used.
    assert found.records and all("nhs_vaccinations" in e and "HTTP 404" in e for e in found.errors)
    by_url = {x.source_url: x for x in found.records}
    ref = by_url[SCHEDULE_URL]
    assert ref.source == "reference" and is_reference_evidence_id(ref.evidence_id)
    # CDC is a stored page: the capture date of the stored version, not "now"
    assert ref.publisher == "CDC" and ref.retrieved_at == STORED_AT
    assert "first dose at 12 through 15 months" in ref.abstract
    assert ref.publication_type == ["Authoritative Reference"] and ref.pmid is None
    # the snapshot holds the full text, under the hash the record carries
    snap = snaps.get(ref.snapshot_sha256)
    assert snap is not None and snap.url == SCHEDULE_URL and ref.abstract in snap.text
    assert text_sha256(snap.text) == ref.snapshot_sha256
    # the ID is built by code from URL, snapshot and passage: stable across runs
    assert ref.evidence_id == reference_evidence_id(SCHEDULE_URL, ref.snapshot_sha256, ref.abstract)
    again = RecordedReferences(books=False).searcher(cfg).search(MMR)
    assert {x.evidence_id for x in again.records} == {x.evidence_id for x in found.records}
    # www.cdc.gov was never requested (it answers 403 to scripts in production)
    assert rec.blocked_requests == [] and found.stored_pages == 2


def test_a_changed_page_gets_a_new_id_and_a_new_snapshot(cfg, tmp_path):
    snaps = InMemorySnapshotStore()
    archive = build_stored_archive(cfg, tmp_path)
    first = RecordedReferences(books=False).searcher(cfg, snapshots=snaps, stored=archive).search(MMR)
    a = next(x for x in first.records if x.source_url == SCHEDULE_URL)
    # the refresh script stores a new version of the publisher's page
    old = archive.current("cdc_child_schedule")
    text = old.text.replace("4 through 6 years", "4 through 7 years")
    archive.add("cdc_child_schedule", FetchedPage(SCHEDULE_URL, old.title, text, text_sha256(text),
                                                  "2026-11-23T09:00:00+00:00"))
    second = RecordedReferences(books=False).searcher(cfg, snapshots=snaps, stored=archive).search(MMR)
    b = next(x for x in second.records if x.source_url == SCHEDULE_URL)
    assert a.snapshot_sha256 != b.snapshot_sha256 and a.evidence_id != b.evidence_id
    assert b.snapshot_sha256 == text_sha256(text) and b.retrieved_at == "2026-11-23T09:00:00+00:00"
    assert snaps.get(a.snapshot_sha256) and snaps.get(b.snapshot_sha256)  # both versions kept
    assert [v["sha256"] for v in archive.history("cdc_child_schedule")] == [a.snapshot_sha256, b.snapshot_sha256]
    # rolling back restores the old version, and with it the old ID
    archive.set_current("cdc_child_schedule", a.snapshot_sha256)
    third = RecordedReferences(books=False).searcher(cfg, stored=archive).search(MMR)
    assert a.evidence_id in {x.evidence_id for x in third.records}


CAFFEINE = "Adults can safely have up to 400 mg of caffeine a day."
FDA_URL = "https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much"


def test_fetched_pages_are_cached(cfg):
    rec = RecordedReferences(books=False)
    searcher = rec.searcher(cfg)
    first = searcher.search(CAFFEINE)
    assert any(x.source_url == FDA_URL for x in first.records)
    searcher.search(CAFFEINE)
    assert rec.calls[FDA_URL] == 1  # served from the cache (failures are not cached)


def test_one_dead_page_does_not_stop_the_others(cfg):
    rec = RecordedReferences(books=False)
    rec.overrides[FDA_URL] = httpx.ConnectError("down")
    found = rec.searcher(cfg).search(CAFFEINE + " That is about four cups of coffee, says the FDA.")
    assert any("fda_caffeine" in e for e in found.errors)
    assert all(x.source_url != FDA_URL for x in found.records)


def test_a_missing_stored_snapshot_is_an_error_and_never_a_request(cfg, tmp_path):
    rec = RecordedReferences(books=False)
    empty = StoredSnapshots(tmp_path / "empty")
    found = rec.searcher(cfg, stored=empty).search(MMR)
    errs = " ".join(found.errors)
    assert "cdc_child_schedule: no stored snapshot" in errs and "refresh_reference_snapshots" in errs
    assert all("cdc.gov" not in (x.source_url or "") for x in found.records)
    assert rec.blocked_requests == []


def test_a_stale_stored_snapshot_is_cited_and_reported(cfg, tmp_path):
    archive = build_stored_archive(cfg, tmp_path, retrieved_at="2026-01-01T00:00:00+00:00")
    now = lambda: datetime(2026, 11, 23, tzinfo=timezone.utc)  # noqa: E731
    found = RecordedReferences(books=False).searcher(cfg, stored=archive, now=now).search(MMR)
    assert any(x.source_url == SCHEDULE_URL for x in found.records)  # still evidence, dated
    assert any("cdc_child_schedule" in e and "stale" in e for e in found.errors)
    fresh = RecordedReferences(books=False).searcher(
        cfg, stored=build_stored_archive(cfg, tmp_path / "fresh", retrieved_at="2026-11-01T00:00:00+00:00"),
        now=now).search(MMR)
    assert not any("stale" in e for e in fresh.errors)


def test_a_stored_snapshot_for_another_url_is_not_cited(cfg, tmp_path):
    archive = build_stored_archive(cfg, tmp_path)
    moved = cfg.model_copy(update={"catalogue": tuple(
        p.model_copy(update={"url": "https://www.cdc.gov/vaccines/moved.html"}) if p.id == "cdc_child_schedule" else p
        for p in cfg.catalogue)})
    found = RecordedReferences(books=False).searcher(moved, stored=archive).search(MMR)
    assert any("cdc_child_schedule" in e and "not the catalogue URL" in e for e in found.errors)
    assert all("child-adolescent" not in (x.source_url or "") for x in found.records)


def test_a_tampered_stored_snapshot_is_refused(cfg, tmp_path):
    archive = build_stored_archive(cfg, tmp_path)
    sha = archive.current_sha("cdc_child_schedule")
    path = tmp_path / "cdc_child_schedule" / f"{sha}.json"
    path.write_text(path.read_text().replace("12 through 15 months", "10 years"))
    found = RecordedReferences(books=False).searcher(cfg, stored=archive).search(MMR)
    assert any("cdc_child_schedule" in e and "does not match its hash" in e for e in found.errors)
    assert all(x.source_url != SCHEDULE_URL for x in found.records)
    assert archive.verify()  # and the archive check reports it


BODY_TEMP = "Normal body temperature is 37 degrees Celsius"


def test_bookshelf_search_through_eutils_never_the_website(cfg):
    rec = RecordedReferences()
    found = rec.searcher(cfg).search(BODY_TEMP)
    books = [x for x in found.records if "ncbi.nlm.nih.gov/books" in (x.source_url or "")]
    fever = next(b for b in books if b.source_url == "https://www.ncbi.nlm.nih.gov/books/NBK562334/")
    assert fever.title == "Physiology, Fever (StatPearls)"
    assert "approximately 37 degrees Celsius" in fever.abstract and fever.publisher.startswith("NCBI")
    assert is_reference_evidence_id(fever.evidence_id) and fever.query == "bookshelf:normal body temperature degrees celsius"
    assert found.candidates.count("NBK562334") == 1
    # only E-utilities: ESearch + EFetch on db=pubmed, never the reCAPTCHA'd book page
    urls = [str(q.url).split("?")[0] for q in rec.requests]
    assert urls == [f"{EUTILS}/esearch.fcgi", f"{EUTILS}/efetch.fcgi"] and rec.blocked_requests == []
    assert rec.requests[0].url.params["sort"] == "relevance"
    assert rec.requests[0].url.params["tool"] == "who_infodemic_monitor"
    # the accession is the document's own, not one from its reference list
    assert all(re.fullmatch(r"https://www\.ncbi\.nlm\.nih\.gov/books/NBK\d+/", b.source_url) for b in books)


def test_bookshelf_chapters_are_cached_and_snapshotted(cfg):
    rec = RecordedReferences()
    snaps = InMemorySnapshotStore()
    searcher = rec.searcher(cfg, snapshots=snaps)
    a = searcher.search(BODY_TEMP)
    b = searcher.search(BODY_TEMP)
    assert len(rec.requests) == 2  # second search served from the cache
    assert [x.evidence_id for x in a.records] == [x.evidence_id for x in b.records]
    for rec_ in a.records:
        snap = snaps.get(rec_.snapshot_sha256)
        assert snap is not None and rec_.abstract in snap.text and snap.url == rec_.source_url


def test_bookshelf_api_key_is_sent_when_configured(cfg):
    rec = RecordedReferences()
    rec.searcher(cfg, api_key="test-key").search(BODY_TEMP)
    assert all(q.url.params.get("api_key") == "test-key" for q in rec.requests)
    rec2 = RecordedReferences()
    rec2.searcher(cfg).search(BODY_TEMP)
    assert all("api_key" not in q.url.params for q in rec2.requests)


def test_bookshelf_retries_ncbi_rate_limit_then_succeeds(cfg):
    rec = RecordedReferences()
    replies = iter([httpx.Response(429, json={"error": "API rate limit exceeded"})])
    original = rec.handler

    def flaky(request):
        if "esearch" in str(request.url):
            nxt = next(replies, None)
            if nxt is not None:
                rec.requests.append(request)
                return httpx.Response(nxt.status_code, content=nxt.content, request=request)
        return original(request)

    rec.handler = flaky  # type: ignore[method-assign]
    slept: list[float] = []
    found = rec.searcher(cfg, sleep=slept.append).search(BODY_TEMP)
    assert slept == [0.5] and any("NBK562334" in (x.source_url or "") for x in found.records)


def test_bookshelf_gives_up_after_the_retry_budget(cfg):
    rec = RecordedReferences()
    rec.overrides[f"{EUTILS}/esearch.fcgi"] = lambda req: httpx.Response(503, request=req)
    found = rec.searcher(cfg, eutils_attempts=2).search(BODY_TEMP)
    assert rec.calls[f"{EUTILS}/esearch.fcgi"] == 2
    assert any("ncbi_bookshelf search" in e and "503" in e for e in found.errors) and not found.records


def test_bookshelf_error_reply_is_an_error(cfg):
    rec = RecordedReferences()
    rec.overrides[f"{EUTILS}/esearch.fcgi"] = lambda req: httpx.Response(
        200, json={"esearchresult": {"ERROR": "Invalid query"}}, request=req)
    found = rec.searcher(cfg).search(BODY_TEMP)
    assert any("Invalid query" in e for e in found.errors)


def test_parse_book_chapters_checks_accessions_and_needs_text():
    xml = """<PubmedArticleSet>
      <PubmedBookArticle><BookDocument><PMID>1</PMID>
        <ArticleIdList><ArticleId IdType="bookaccession">https://evil.example/x</ArticleId></ArticleIdList>
        <ArticleTitle>Bad accession</ArticleTitle>
        <Abstract><AbstractText>Normal body temperature text.</AbstractText></Abstract></BookDocument>
      </PubmedBookArticle>
      <PubmedBookArticle><BookDocument><PMID>2</PMID>
        <ArticleIdList><ArticleId IdType="bookaccession">NBK2</ArticleId></ArticleIdList>
        <ArticleTitle>No summary</ArticleTitle></BookDocument>
      </PubmedBookArticle>
      <PubmedBookArticle><BookDocument><PMID>3</PMID>
        <ArticleIdList><ArticleId IdType="bookaccession">NBK3</ArticleId></ArticleIdList>
        <Book><BookTitle>GeneReviews</BookTitle></Book><ArticleTitle>Good <i>one</i></ArticleTitle>
        <Abstract><AbstractText Label="SUMMARY">First <b>part</b>.</AbstractText>
          <AbstractText Label="DIAGNOSIS">Second part.</AbstractText></Abstract>
        <ReferenceList><Reference><ArticleIdList><ArticleId IdType="bookaccession">NBK999</ArticleId>
        </ArticleIdList></Reference></ReferenceList></BookDocument>
      </PubmedBookArticle>
      <PubmedArticle><MedlineCitation><PMID>4</PMID></MedlineCitation></PubmedArticle>
    </PubmedArticleSet>"""
    chapters = parse_book_chapters(xml)
    assert [c.pmid for c in chapters] == ["3"]
    c = chapters[0]
    assert c.accession == "NBK3" and c.citation_title == "Good one (GeneReviews)"
    assert c.text == "SUMMARY: First part.\n\nDIAGNOSIS: Second part."
    with pytest.raises(ReferenceFetchError):
        parse_book_chapters("<not xml")


def test_off_topic_pages_give_no_record(cfg):
    # The recorded Bookshelf reply answers every search with the same two chapters; they
    # are fetched (and snapshotted) but share too few words with this claim to be quoted.
    found = RecordedReferences().searcher(cfg).search("Garlic cures warts")
    assert found.pages_fetched == 2 and found.records == [] and not found.errors


def test_snapshot_store_rejects_text_that_does_not_match_its_hash():
    page = FetchedPage("https://www.cdc.gov/x", "t", "text", "0" * 64, "2026-11-22T00:00:00+00:00")
    with pytest.raises(SnapshotMismatch):
        InMemorySnapshotStore().save(page)


def test_sql_snapshot_store_round_trip_and_duplicate_save():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.retrieval.references import SqlSnapshotStore
    from app.db.base import Base
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = SqlSnapshotStore(sessionmaker(bind=engine))
    text = "Children need two doses."
    page = FetchedPage(SCHEDULE_URL, "t", text, text_sha256(text), "2026-11-22T00:00:00+00:00")
    store.save(page)
    store.save(page)  # idempotent
    snap = store.get(page.sha256)
    assert snap is not None and snap.text == text and snap.url == SCHEDULE_URL
    assert store.get("f" * 64) is None


# ==================================================================== claim_kind


@pytest.mark.parametrize("text,category,kind", [
    ("Drinking hot water cures the flu", "treatment_efficacy", "research_question"),
    ("Vaccines cause autism", "causation", "research_question"),
    ("Vitamin C cuts your risk by 50%", "prevention", "research_question"),
    ("The MMR vaccine is given at 12 months", "prevention", "fact_of_record"),
    ("Adults can safely have up to 400 mg of caffeine a day", "safety", "fact_of_record"),
    ("Measles kills 100,000 people every year", "other", "fact_of_record"),
    ("Normal body temperature is 37 degrees", "other", "fact_of_record"),
    ("An egg contains 6 grams of protein", "nutrition", "fact_of_record"),
    ("1 in 3 adults has high blood pressure", "statistic", "fact_of_record"),
    ("This tea is amazing", "other", "research_question"),
])
def test_claim_kind_rules(text, category, kind):
    assert infer_claim_kind(text, category) == kind


def test_model_claim_kind_wins_when_valid():
    assert resolve_claim_kind("fact_of_record", "Garlic stops colds") == "fact_of_record"
    assert resolve_claim_kind("FACT_OF_RECORD ", "Garlic stops colds") == "fact_of_record"
    assert resolve_claim_kind("a_guess", "The MMR vaccine is given at 12 months") == "fact_of_record"
    assert resolve_claim_kind(None, "Garlic stops colds") == "research_question"


def test_old_claims_default_to_research_questions():
    c = GraphClaim(claim_id="c1", claim_text="x", claim_category="other", source_segment_ids=["t1"],
                   start_seconds=0, end_seconds=1)
    assert c.claim_kind == "research_question"


def _extract_state(*texts: str) -> dict:
    segs = [FusedSegment(segment_id=f"f{i}", start=i, end=i + 1, spoken=t, sources=[f"t{i}"])
            for i, t in enumerate(texts, start=1)]
    ts = [TranscriptSegment(segment_id=f"t{i}", start=i, end=i + 1, text=t) for i, t in enumerate(texts, start=1)]
    return {"fused_segments": segs, "transcript_segments": ts, "ocr_segments": []}


class _Caller:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def call(self, step, input, *, system=None):
        self.requests.append((step, input, system))
        return SimpleNamespace(output=self.output, record=SimpleNamespace(model="m", prompt_version="extract_v2"))


def test_extractor_records_claim_kind_from_the_model_or_the_rules():
    texts = ["The MMR vaccine is given at 12 months.", "Garlic stops colds.", "Lemon water detoxes the liver."]
    caller = _Caller({"claims": [
        {"claim_text": texts[0], "claim_category": "prevention", "source_segment_ids": ["f1"]},  # none given
        {"claim_text": texts[1], "claim_category": "prevention", "source_segment_ids": ["f2"],
         "claim_kind": "fact_of_record"},                                                         # model's
        {"claim_text": texts[2], "claim_category": "other", "source_segment_ids": ["f3"],
         "claim_kind": "nonsense"},                                                               # invalid
    ]})
    out = cl.make_extract_claims(caller)(_extract_state(*texts))
    kinds = {c.claim_text: c.claim_kind for c in out["claims"]}
    assert kinds == {texts[0]: "fact_of_record", texts[1]: "fact_of_record", texts[2]: "research_question"}
    step, request, system = caller.requests[0]
    props = request["tools"][0]["input_schema"]["properties"]["claims"]["items"]["properties"]
    assert props["claim_kind"]["enum"] == ["research_question", "fact_of_record"]
    assert "claim_kind" in system and "fact_of_record" in system  # extract_v2 explains it


# ======================================================================= rerank


def _paper(i: int, title: str, abstract: str, types=("Systematic Review",)) -> EvidenceRecord:
    return EvidenceRecord(evidence_id=f"ev_{i}", source="pubmed", pmid=str(i), title=title, abstract=abstract,
                          publication_type=list(types))


def _ref(passage: str, title: str = "Immunization schedule") -> EvidenceRecord:
    return EvidenceRecord(evidence_id=reference_evidence_id("https://www.cdc.gov/x", "a" * 64, passage),
                          source="reference", title=title, abstract=passage,
                          publication_type=["Authoritative Reference"], source_url="https://www.cdc.gov/x",
                          publisher="CDC", retrieved_at="2026-11-22T00:00:00+00:00", snapshot_sha256="a" * 64)


def test_reference_is_its_own_study_type():
    r_ = _ref("Children need two doses of MMR vaccine.")
    assert classify_study(r_) == StudyType.REFERENCE
    assert evidence_class(StudyType.REFERENCE) == EvidenceClass.AUTHORITATIVE_REFERENCE


def test_official_source_outranks_studies_for_facts_of_record_but_not_for_efficacy():
    claim = "The MMR vaccine is given in two doses at 12 months and 4 years"
    ref = _ref("Children need two doses of MMR vaccine: the first dose at 12 through 15 months and the second "
               "at 4 through 6 years.")
    sr = _paper(1, "MMR vaccine doses at 12 months and 4 years: a systematic review",
                "MMR vaccine given in two doses at 12 months and 4 years in children. Systematic review.")
    fact = Reranker().rerank(claim, [sr, ref], "fact_of_record").kept
    assert [x.evidence_id for x in fact] == [ref.evidence_id, sr.evidence_id]
    research = Reranker().rerank(claim, [ref, sr], "research_question").kept
    assert [x.evidence_id for x in research] == [sr.evidence_id, ref.evidence_id]
    assert Reranker().rerank(claim, [ref, sr]).kept[0].evidence_id == sr.evidence_id  # no kind: studies first


def test_off_topic_reference_is_dropped_by_the_threshold():
    claim = "The MMR vaccine is given at 12 months"
    off = _ref("Wash your hands with soap for twenty seconds.", title="Handwashing")
    res = Reranker().rerank(claim, [off], "fact_of_record")
    assert res.kept == [] and res.dropped_below_threshold == [off.evidence_id]


# =============================================================== retrieval nodes


def _claim(cid: str, text: str, kind: str) -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category="other", source_segment_ids=["t1"],
                      start_seconds=0, end_seconds=1, claim_kind=kind)


class _SpySearcher:
    def __init__(self, inner=None, fail: Exception | None = None):
        self.inner, self.fail, self.calls = inner, fail, []

    def search(self, text):
        self.calls.append(text)
        if self.fail:
            raise self.fail
        return self.inner.search(text)


def _retrieval_state(*claims: GraphClaim) -> dict:
    return {"claims": list(claims), "retrieval_queries": {}, "retrieved_evidence": {}, "retrieval_attempts": {}}


def test_facts_of_record_get_references_alongside_pubmed_research_questions_do_not(cfg):
    spy = _SpySearcher(RecordedReferences(books=False).searcher(cfg))
    nodes = make_retrieval_nodes(EvidenceRetriever(RecordedPubMed().client()), references=spy)
    state = _retrieval_state(_claim("c1", MMR, "fact_of_record"),
                             _claim("c2", "Drinking hot water every morning cures the flu.", "research_question"))
    state.update(nodes[r.PLAN_RETRIEVAL](state))
    state.update(nodes[r.RETRIEVE_EVIDENCE](state))
    assert spy.calls == [MMR]  # the research question never touched the references
    c1 = state["retrieved_evidence"]["c1"]
    assert any(x.source == "reference" for x in c1)
    assert all(x.source == "pubmed" for x in state["retrieved_evidence"]["c2"])
    assert state["retrieval_attempts"] == {"c1": 1, "c2": 1}  # PubMed ran too, same round

    # second round (e.g. the critic asked for more): references are not searched again
    state.update(nodes[r.PLAN_RETRIEVAL](state))
    state.update(nodes[r.RETRIEVE_EVIDENCE](state))
    assert spy.calls == [MMR]

    # rerank passes the kind: references first for the fact of record
    out = nodes[r.RERANK_EVIDENCE](state)
    assert out["reranked_evidence"]["c1"][0].source == "reference"


def test_reference_failure_is_recorded_and_pubmed_still_runs():
    spy = _SpySearcher(fail=RuntimeError("boom"))
    pub = RecordedPubMed()
    nodes = make_retrieval_nodes(EvidenceRetriever(pub.client()), references=spy)
    state = _retrieval_state(_claim("c1", MMR, "fact_of_record"))
    state.update(nodes[r.PLAN_RETRIEVAL](state))
    out = nodes[r.RETRIEVE_EVIDENCE](state)
    assert any("reference search failed" in e.message for e in out["errors"])
    assert out["retrieval_attempts"]["c1"] == 1 and pub.calls["esearch"] >= 1


def test_without_a_searcher_retrieval_is_unchanged():
    pub = RecordedPubMed()
    nodes = make_retrieval_nodes(EvidenceRetriever(pub.client()))
    state = _retrieval_state(_claim("c1", MMR, "fact_of_record"))
    state.update(nodes[r.PLAN_RETRIEVAL](state))
    out = nodes[r.RETRIEVE_EVIDENCE](state)
    assert all(x.source == "pubmed" for x in out["retrieved_evidence"]["c1"])


# ============================================================ same verdict rules


def test_verifier_prompt_v2_states_the_reference_rules():
    prompt = load_prompt("verify_v2")
    assert 'source "reference"' in prompt
    assert "absence of evidence" in prompt.lower() and "INSUFFICIENT_EVIDENCE" in prompt
    assert "outranks any single study" in prompt
    index = evidence_index([_ref("Children need two doses of MMR vaccine.")])
    assert "source: reference" in index and "publisher: CDC" in index and "retrieved: 2026-11-22" in index


def test_judge_explanation_check_covers_reference_ids():
    ok = _ref("Children need two doses.").evidence_id
    d = Decision(label=MisinfoLabel.MISINFO, rule="endorsed_false", deciding=(), evidence_ids=(ok,),
                 review_flags=())
    check_explanation(f"MISINFO: {ok} gives a different schedule.", d)
    with pytest.raises(InvalidExplanation):
        check_explanation(f"MISINFO: see ref_{'0' * 16}.", d)


def _fact_script(step, inp):
    if step == "extract_claims":
        out = default_script(step, inp)
        for c in out["claims"]:
            c["claim_category"] = "other"
            c["claim_kind"] = "fact_of_record"
        return out
    if step == "verify_claims":
        text = inp["messages"][0]["content"]
        refs = re.findall(r"^- id: (ref_[0-9a-f]{16}) \| source: reference", text, re.M)
        if refs:
            return {"verdict": "CONTRADICTED", "supporting_evidence_ids": [], "contradicting_evidence_ids": refs[:1],
                    "explanation": "The schedule gives two doses, the first at 12 to 15 months.",
                    "limitations": [], "raw_confidence": 0.9}
        return {"verdict": "INSUFFICIENT_EVIDENCE", "supporting_evidence_ids": [], "contradicting_evidence_ids": [],
                "explanation": "Nothing tests this.", "limitations": [], "raw_confidence": 0.3}
    return default_script(step, inp)


def _mmr_fusion():
    from app.core.schemas.pipeline import FusionResult

    meta = {"ocr_disabled": True, "transcript_segments": [{"start": 1.0, "end": 5.0, "text": MMR}]}
    return FusionResult(transcript=MMR, visual_text="", combined_content=MMR, metadata=meta)


def test_end_to_end_a_fact_of_record_contradicted_by_a_reference_is_misinfo(cfg):
    from app.db.models.claim import ClaimEvidenceRow, ClaimRow, EvidenceRecordRow
    from app.services.pipeline_result_service import persist_outcome

    snaps = InMemorySnapshotStore()
    provider = gp.GraphProvider(
        caller=make_router(ScriptedClient(_fact_script)),
        retriever=EvidenceRetriever(RecordedPubMed().client()), fallback=FakeSingleCall(),
        references=RecordedReferences(books=False).searcher(cfg, snapshots=snaps),
    )
    outcome = provider.run(_mmr_fusion(), job_id="job-1", video_id="vid-1")
    assert outcome.pipeline == "graph" and not outcome.fallback_used
    final = outcome.state["final_result"]
    assert final.classification == MisinfoLabel.MISINFO
    assert any(is_reference_evidence_id(e) for e in final.evidence_ids)
    v = outcome.state["verification_results"]["c1"]
    assert v.contradicting_evidence_ids and is_reference_evidence_id(v.contradicting_evidence_ids[0])
    assert outcome.state["claims"][0].claim_kind == "fact_of_record"

    db = _db()
    _job(db)
    persist_outcome(db, "job-1", _mmr_fusion(), outcome)
    assert db.query(ClaimRow).one().claim_kind == "fact_of_record"
    row = db.query(EvidenceRecordRow).filter_by(evidence_id=v.contradicting_evidence_ids[0]).one()
    assert row.source == "reference" and row.publisher == "CDC" and row.retrieved_at
    assert snaps.get(row.snapshot_sha256) is not None
    link = db.query(ClaimEvidenceRow).filter_by(evidence_pk=row.id).one()
    assert link.relation == "CONTRADICTS"


def test_reference_sources_are_off_by_default():
    from app.core.config import Settings

    s = Settings()
    assert s.USE_REFERENCE_SOURCES is False
    assert gp.reference_searcher(s) is None


def test_migration_0009_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.db.models.claim import ReferenceSnapshotRow

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    acfg = Config(str(BACKEND / "alembic.ini"))
    acfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    command.upgrade(acfg, "0009")
    insp = inspect(create_engine(url))
    assert "reference_snapshots" in insp.get_table_names()
    assert {c.name for c in ReferenceSnapshotRow.__table__.columns} <= {
        c["name"] for c in insp.get_columns("reference_snapshots")}
    assert {"publisher", "retrieved_at", "snapshot_sha256"} <= {c["name"] for c in insp.get_columns("evidence_records")}
    assert "claim_kind" in {c["name"] for c in insp.get_columns("claims")}
    command.downgrade(acfg, "0008")
    insp = inspect(create_engine(url))
    assert "reference_snapshots" not in insp.get_table_names()
    assert "claim_kind" not in {c["name"] for c in insp.get_columns("claims")}


# ==================================================================== MCP contract


def test_mcp_tools_keep_the_v1_record_and_refuse_references():
    from app.mcp_server import schemas as S

    core = _ref("Children need two doses.")
    with pytest.raises(ValueError):
        S.EvidenceRecord.model_validate(core.model_dump())  # source "reference" is not in contract v1
    paper = _paper(1, "t", "a")
    assert S.EvidenceRecord.model_validate(paper.model_dump()).to_core() == paper
