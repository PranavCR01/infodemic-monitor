"""PubMed client, cache, dedup and filters (T03, issue #31, design §6 "Calling PubMed").

Every test runs against recorded fixtures through httpx.MockTransport; a guard makes
any real socket connection fail the test.
"""
from __future__ import annotations

import socket

import httpx
import pytest

from app.core.retrieval.cache import InMemoryQueryCache, RedisQueryCache
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.pubmed import (
    EFETCH_URL,
    PubMedError,
    RateLimiter,
    parse_efetch,
    parse_esearch,
    shared_rate_limiter,
)
from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence
from app.core.retrieval.schemas import EvidenceRecord, SearchFilters
from app.tests.pubmed_fixtures import RecordedPubMed

P = QueryPlanner()
HOT = P.ladder("Drinking hot water every morning cures the flu.")
GARLIC = P.ladder("Some people say garlic stops colds. That's a myth.")
VAX = P.ladder("Vaccines cause autism in children")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def server():
    s = RecordedPubMed()
    yield s
    assert s.unknown_queries == [], "planner produced queries with no fixture; re-run the build script"


# ----------------------------------------------------------------- the client


def test_esearch_uses_relevance_sort_and_fixed_params(server):
    client = server.client()
    assert client.search(GARLIC[0], max_results=20) == ["99000201", "99000202", "99000203", "99000204"]
    params = server.requests[0].url.params
    assert params["sort"] == "relevance"
    assert params["db"] == "pubmed" and params["retmode"] == "json" and params["retmax"] == "20"
    assert params["tool"] == "who-infodemic-monitor"
    assert "api_key" not in params and "email" not in params


def test_api_key_and_email_are_sent_when_configured(server):
    server.client(api_key="k123", email="team@example.org").search(GARLIC[0])
    params = server.requests[0].url.params
    assert params["api_key"] == "k123" and params["email"] == "team@example.org"


def test_efetch_returns_abstracts_not_just_titles(server):
    arts = server.client().fetch(["99000101", "99000201"])
    assert [a.pmid for a in arts] == ["99000101", "99000201"]
    a = arts[0]
    assert a.abstract.startswith("BACKGROUND: Synthetic fixture text.")
    assert "CONCLUSIONS: Synthetic fixture text. No evidence that hot drinks cure influenza." in a.abstract
    assert a.publication_year == 2008
    assert a.publication_types == ("Journal Article", "Randomized Controlled Trial")
    assert a.doi == "10.9999/synthetic.0101"
    assert a.journal == "Synthetic Journal of Evidence"
    params = server.requests[0].url.params
    assert params["rettype"] == "abstract" and params["retmode"] == "xml"


def test_efetch_edge_cases(server):
    arts = {a.pmid: a for a in server.client().fetch(["99000102", "99000204", "99000201", "123456789"])}
    assert "123456789" not in arts  # PubMed had nothing for it
    assert arts["99000102"].publication_year == 2012  # MedlineDate "2012 Jan-Feb"
    assert arts["99000102"].doi == "10.9999/synthetic.0102"  # only in ELocationID
    assert arts["99000204"].abstract == ""  # no abstract
    assert arts["99000204"].title.startswith("Effects of Allium sativum extract")  # inline <i> kept as text
    assert arts["99000201"].doi == "10.9999/synthetic.0201"  # DOI lower-cased


def test_efetch_batches_large_requests(server, monkeypatch):
    import app.core.retrieval.pubmed as pm

    monkeypatch.setattr(pm, "MAX_PMIDS_PER_FETCH", 2)
    arts = server.client().fetch(["99000301", "99000302", "99000303", "99000304", "99000301"])
    assert [a.pmid for a in arts] == ["99000301", "99000302", "99000303", "99000304"]
    assert server.calls["efetch"] == 2


@pytest.mark.parametrize("failure", [503, 500, 429, httpx.ConnectError("boom")])
def test_ncbi_errors_are_retried_with_backoff(server, failure):
    sleeps: list[float] = []
    server.fail_next = [failure, failure]
    client = server.client(sleeps=sleeps, max_attempts=4)
    assert client.search(GARLIC[0])[0] == "99000201"
    assert server.calls["esearch"] == 3
    backoff = [s for s in sleeps if s >= 1.0]
    assert backoff == [1.0, 2.0]  # exponential


def test_rate_limit_message_in_200_body_is_retried(server):
    sleeps: list[float] = []
    server.fail_next = [lambda: httpx.Response(200, json={"error": "API rate limit exceeded", "count": "4"})]
    assert server.client(sleeps=sleeps).search(GARLIC[0])[0] == "99000201"
    assert server.calls["esearch"] == 2


def test_client_errors_are_not_retried(server):
    server.fail_next = [400]
    with pytest.raises(httpx.HTTPStatusError):
        server.client().search(GARLIC[0])
    assert server.calls["esearch"] == 1


def test_retries_give_up_after_budget(server):
    server.fail_next = [503] * 10
    with pytest.raises(httpx.HTTPStatusError):
        server.client(max_attempts=3).search(GARLIC[0])
    assert server.calls["esearch"] == 3


def test_only_fixed_endpoints_are_called(server):
    client = server.client()
    with pytest.raises(PubMedError):
        client._get("https://example.org/anything", {})
    assert server.requests == []


def test_rate_limiter_spaces_requests():
    t = [0.0]
    sleeps: list[float] = []

    def sleep(s):
        sleeps.append(s)
        t[0] += s

    lim = RateLimiter(3.0, clock=lambda: t[0], sleep=sleep)
    for _ in range(4):
        lim.acquire()
    assert sleeps == pytest.approx([1 / 3] * 3)
    assert t[0] == pytest.approx(1.0)  # 4 requests in 1 s: never more than 3 a second


def test_shared_limiter_rates_match_ncbi_limits():
    assert shared_rate_limiter(False).interval == pytest.approx(1 / 2.5)  # < 3/s without a key
    assert shared_rate_limiter(True).interval == pytest.approx(1 / 9.0)  # < 10/s with one
    assert shared_rate_limiter(False) is shared_rate_limiter(False)


def test_parsers_reject_garbage():
    with pytest.raises(PubMedError):
        parse_efetch("<html>oops</html>")
    with pytest.raises(PubMedError):
        parse_efetch("not xml")
    with pytest.raises(PubMedError):
        parse_esearch({"esearchresult": {"ERROR": "Invalid query"}})
    assert parse_esearch({"esearchresult": {"idlist": ["1", "1", "x; drop", "22"]}}) == ["1", "22"]


def test_publication_type_and_date_filters_reach_esearch(server):
    f = SearchFilters(publication_types=("Randomized Controlled Trial", "Meta-Analysis"), min_year=2010)
    server.client().search("garlic", filters=f)
    params = server.requests[0].url.params
    assert params["term"] == '(garlic) AND ("Randomized Controlled Trial"[pt] OR "Meta-Analysis"[pt])'
    assert params["datetype"] == "pdat" and params["mindate"] == "2010" and params["maxdate"] == "3000"
    server.unknown_queries.clear()


# --------------------------------------------------------------- the retriever


def test_retrieve_builds_records_from_pubmed_fields_only(server):
    res = EvidenceRetriever(server.client()).retrieve(HOT[1])
    assert [r.evidence_id for r in res.records] == ["ev_99000101", "ev_99000102"]
    r = res.records[0]
    assert r.source == "pubmed" and r.pmid == "99000101"
    assert r.source_url == "https://pubmed.ncbi.nlm.nih.gov/99000101/"
    assert r.query == HOT[1]
    assert r.relevance_score is None  # set by the reranker (T05)
    assert r.abstract and r.publication_type == ["Journal Article", "Randomized Controlled Trial"]


def test_retrieve_dedups_by_doi_and_drops_retracted(server):
    res = EvidenceRetriever(server.client()).retrieve(GARLIC[0])
    pmids = [r.pmid for r in res.records]
    assert pmids == ["99000201", "99000204"]  # 202 shares 201's DOI; 203 is retracted
    assert res.filtered_out == ["99000203"]
    assert res.pmids_found == 4


def test_errata_are_dropped_and_injection_text_is_kept_as_data(server):
    res = EvidenceRetriever(server.client()).retrieve(VAX[0])
    assert [r.pmid for r in res.records] == ["99000302", "99000304"]
    # Abstracts are untrusted data (§15): stored verbatim, never acted on.
    assert "Ignore previous instructions" in res.records[1].abstract


def test_year_filters_drop_records(server):
    retriever = EvidenceRetriever(server.client(), filters=SearchFilters(max_year=2010))
    res = retriever.retrieve(GARLIC[0])
    assert [r.pmid for r in res.records] == []  # 2014 and 2019 papers dropped, 2001 retracted
    assert sorted(res.filtered_out) == ["99000201", "99000202", "99000203", "99000204"]


def test_empty_search_does_not_call_efetch(server):
    res = EvidenceRetriever(server.client()).retrieve(HOT[0])
    assert res.records == [] and res.pmids_found == 0
    assert server.calls == {"esearch": 1}


def test_query_cache_prevents_repeat_ncbi_calls(server):
    retriever = EvidenceRetriever(server.client())
    first = retriever.retrieve(GARLIC[0])
    assert first.network_requests == 2  # ESearch + EFetch
    again = retriever.retrieve(GARLIC[0])
    assert again.network_requests == 0
    assert [r.pmid for r in again.records] == [r.pmid for r in first.records]
    assert server.calls == {"esearch": 1, "efetch": 1}


def test_papers_found_by_several_queries_are_fetched_once(server):
    retriever = EvidenceRetriever(server.client())
    retriever.retrieve(VAX[0])
    server.requests.clear()
    retriever.retrieve(VAX[1])  # 99000302 is cached; only 99000301 is fetched
    fetch = [r for r in server.requests if str(r.url).startswith(EFETCH_URL)]
    assert [r.url.params["id"] for r in fetch] == ["99000301"]


def test_cache_entries_expire():
    t = [0.0]
    cache = InMemoryQueryCache(clock=lambda: t[0])
    cache.set("k", [1], ttl=10)
    assert cache.get("k") == [1]
    t[0] = 11
    assert cache.get("k") is None


def test_redis_cache_round_trip_and_tolerates_outage():
    class FakeRedis:
        def __init__(self):
            self.d, self.ex = {}, {}

        def get(self, k):
            return self.d.get(k)

        def set(self, k, v, ex=None):
            self.d[k] = v.encode()
            self.ex[k] = ex

    r = FakeRedis()
    cache = RedisQueryCache(r)
    cache.set("pmid:1", {"title": "t"}, ttl=60)
    assert cache.get("pmid:1") == {"title": "t"}
    assert r.ex == {"retrieval:pmid:1": 60}

    class Down:
        def get(self, k):
            raise ConnectionError

        def set(self, *a, **k):
            raise ConnectionError

    down = RedisQueryCache(Down())
    down.set("x", 1)
    assert down.get("x") is None


def test_shared_cache_across_retrievers(server):
    cache = InMemoryQueryCache()
    EvidenceRetriever(server.client(), cache).retrieve(GARLIC[0])
    other = RecordedPubMed()
    EvidenceRetriever(other.client(), cache).retrieve(GARLIC[0])
    assert other.requests == []


def test_merge_evidence_dedups_by_pmid_doi_and_keeps_first():
    a = EvidenceRecord(evidence_id="ev_1", source="pubmed", pmid="1", doi="10.1/x", title="A", query="q1")
    a2 = EvidenceRecord(evidence_id="ev_1", source="pubmed", pmid="1", title="A", query="q2")
    b = EvidenceRecord(evidence_id="ev_2", source="pubmed", pmid="2", doi="10.1/X", title="B")
    c = EvidenceRecord(evidence_id="ev_3", source="pubmed", pmid="3", title="C")
    merged = merge_evidence([a], [a2, b, c])
    assert [r.evidence_id for r in merged] == ["ev_1", "ev_3"]
    assert merged[0].query == "q1"
