"""Retrieval MCP server (target design §6 "Retrieval as a shared service", §15 "MCP clients").

Acceptance criteria, from the design doc (no GitHub issue for T13):

- one implementation: ``app.core.retrieval`` has no MCP code; the server is a thin
  wrapper and returns exactly what the in-process functions return;
- the five tools of the §6 table, Pydantic input and output, published as JSON Schema,
  results as structured data;
- Streamable HTTP with a per-client token and per-tool scopes (``search_library`` its
  own scope);
- one NCBI quota for everyone (a shared token bucket, Redis in production) and a
  per-client share, so one client can't starve another; a shared query cache;
- limits: results per call, timeouts, payload size caps;
- tool names and schemas are a contract checked in CI;
- abstracts and library chunks are marked untrusted.

PubMed is served from the recorded fixtures (``fixtures/pubmed``); no network.
"""
from __future__ import annotations

import ast
import asyncio
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

mcp = pytest.importorskip("mcp", reason="the MCP SDK is the optional [mcp] extra")

from mcp import Client  # noqa: E402

from app.core.retrieval.cache import InMemoryQueryCache  # noqa: E402
from app.core.retrieval.library import HashingEmbedder, InMemoryLibraryStore, LibraryConfig, LibrarySearcher  # noqa: E402
from app.core.retrieval.library.store import LibraryDocument, StoredChunk  # noqa: E402
from app.core.retrieval.mesh import map_to_mesh  # noqa: E402
from app.core.retrieval.pubmed import RateLimiter  # noqa: E402
from app.core.retrieval.rerank import Reranker  # noqa: E402
from app.core.retrieval.retriever import EvidenceRetriever, to_evidence  # noqa: E402
from app.core.retrieval.schemas import EvidenceRecord  # noqa: E402
from app.mcp_server import contract as C  # noqa: E402
from app.mcp_server import schemas as S  # noqa: E402
from app.mcp_server.config import (  # noqa: E402
    ALL_SCOPES,
    TOOL_NAMES,
    ClientConfig,
    ConfigError,
    hash_token,
    load_clients,
    load_config,
    parse_clients,
    scope_for,
)
from app.mcp_server.quota import (  # noqa: E402
    Bucket,
    BucketLimiter,
    InMemoryBucketStore,
    QuotaExceeded,
    RedisBucketStore,
    ncbi_client_bucket,
    ncbi_global_bucket,
    pipeline_ncbi_limiter,
)
from app.mcp_server.server import build_server, http_app  # noqa: E402
from app.mcp_server.service import RetrievalToolService, ToolCallError  # noqa: E402
from app.tests.pubmed_fixtures import RecordedPubMed  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
# search_02 in the recorded fixtures (search_01 is an empty result on purpose).
HOT_WATER_QUERY = 'Beverages[MeSH Terms] AND "Respiratory Tract Infections"[MeSH Terms]'
GARLIC_QUERY = (
    '(Garlic[MeSH Terms] OR garlic[tiab] OR allicin[tiab]) AND ("Common Cold"[MeSH Terms] OR "common cold"[tiab])'
)
TOKENS = {"pipeline-team": "tok-pipeline-0123456789", "other-team": "tok-other-0123456789"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "localhost", "::1"):  # the local redis-server test only
            return real_connect(self, address, *a, **k)
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", guarded)


def client_cfg(client_id="other-team", scopes=ALL_SCOPES, share=0.2, cpm=None) -> ClientConfig:
    return ClientConfig(client_id=client_id, token_sha256=hash_token(TOKENS.get(client_id, client_id + "-tok")),
                        scopes=tuple(scopes), ncbi_share=share, calls_per_minute=cpm)


def make_config(**limits):
    cfg = load_config()
    if limits:
        cfg = cfg.model_copy(update={"limits": cfg.limits.model_copy(update=limits)})
    return cfg


def make_library() -> LibrarySearcher:
    store = InMemoryLibraryStore()
    emb = HashingEmbedder()
    docs = [
        ("doc1", "Garlic supplementation and the common cold", "rct",
         "A daily allicin garlic supplement reduced the number of common colds in adults compared with placebo."),
        ("doc2", "Citrus intake and cancer incidence", "observational",
         "Lemon and citrus consumption was not associated with cancer incidence in a cohort of women."),
    ]
    for doc_id, title, st, text in docs:
        store.save_document(LibraryDocument(document_id=doc_id, title=title, sha256=doc_id * 8, year=2010,
                                            study_type=st))
        vec = emb.embed_documents([(title, text)])[0]
        store.add_chunks([StoredChunk(f"{doc_id}_c0", doc_id, 1, 0, text, 30, tuple(vec),
                                      emb.model_name, emb.model_version)])
    return LibrarySearcher(store, emb, LibraryConfig())


@pytest.fixture
def recorded():
    return RecordedPubMed()


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_service(recorded, *, library=True, quota=None, cache=None, config=None, **kw):
    """Quota waits run on a fake clock, so tests don't sleep."""
    clock = FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(recorded.handler))
    return RetrievalToolService(
        config or make_config(), quota_store=quota or InMemoryBucketStore(clock=clock),
        cache=cache or InMemoryQueryCache(), http=http, library_searcher=make_library() if library else None,
        sleep=clock.sleep, **kw,
    )


def registry(*clients: ClientConfig):
    from app.mcp_server.config import ClientRegistry

    return ClientRegistry(clients=tuple(clients))


def call(server, tool: str, args: dict):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go())


@pytest.fixture
def service(recorded):
    return make_service(recorded)


@pytest.fixture
def local_server(service):
    me = client_cfg()
    return build_server(service, registry(me), local_client=me)


def sample_records() -> list[EvidenceRecord]:
    rec = RecordedPubMed()
    http = httpx.Client(transport=httpx.MockTransport(rec.handler))
    from app.core.retrieval.pubmed import PubMedClient

    r = EvidenceRetriever(PubMedClient(http, rate_limiter=RateLimiter(1000.0)), InMemoryQueryCache())
    return r.retrieve(GARLIC_QUERY).records


# ============================================== one implementation, two front ends


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_retrieval_package_has_no_mcp_or_langgraph_code():
    for py in (BACKEND / "app" / "core" / "retrieval").rglob("*.py"):
        mods = _imports(py)
        bad = {m for m in mods if m.split(".")[0] in ("mcp", "langgraph") or m.startswith("app.mcp_server")}
        assert not bad, f"{py.relative_to(BACKEND)} imports {bad}"


def test_pipeline_does_not_depend_on_the_mcp_server():
    for py in (BACKEND / "app" / "core").rglob("*.py"):
        assert not any(m.startswith("app.mcp_server") for m in _imports(py)), py
    for py in (BACKEND / "app" / "worker").rglob("*.py"):
        assert not any(m.startswith("app.mcp_server") or m.split(".")[0] == "mcp" for m in _imports(py)), py


def test_service_layer_has_no_mcp_imports():
    for name in ("service.py", "config.py", "quota.py", "schemas.py"):
        mods = _imports(BACKEND / "app" / "mcp_server" / name)
        assert not {m for m in mods if m.split(".")[0] == "mcp"}, name


def test_importing_the_package_does_not_need_the_sdk():
    code = "import sys; import app.mcp_server, app.mcp_server.service; print('mcp' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ===================================================================== the tools


def test_the_five_tools_with_input_and_output_schemas(local_server):
    tools = asyncio.run(local_server.list_tools())
    assert sorted(t.name for t in tools) == sorted(TOOL_NAMES)
    for t in tools:
        assert t.input_schema["type"] == "object"
        assert t.output_schema and t.output_schema["type"] == "object", t.name  # structured results
        assert t.annotations.read_only_hint is True


def test_tool_parameters_match_the_input_models(local_server):
    from app.mcp_server.service import INPUT_MODELS

    tools = {t.name: t for t in asyncio.run(local_server.list_tools())}
    for name, model in INPUT_MODELS.items():
        published = C.normalize(tools[name].input_schema)
        expected = C.normalize(model.model_json_schema())
        assert published["properties"] == expected["properties"], name
        assert set(published.get("required", [])) == set(expected.get("required", [])), name


def test_map_to_mesh_matches_the_in_process_function(local_server):
    text = "Drinking hot water cures the flu in children"
    r = call(local_server, "map_to_mesh", {"text": text})
    assert not r.is_error
    expected = S.MeshMapping(concepts=map_to_mesh(text)).model_dump(mode="json")
    assert r.structured_content == expected
    assert {c["mesh"] for c in r.structured_content["concepts"]} >= {"Influenza, Human", "Child"}


def test_search_pubmed_matches_the_retriever_and_sorts_by_relevance(local_server, recorded):
    r = call(local_server, "search_pubmed", {"query": HOT_WATER_QUERY, "max_results": 20})
    assert not r.is_error, r.content
    ref = RecordedPubMed()
    direct = EvidenceRetriever(ref.client(), InMemoryQueryCache(), max_results=20).search(HOT_WATER_QUERY)
    assert r.structured_content["pmids"] == direct and direct
    assert r.structured_content["cached"] is False
    assert recorded.requests[0].url.params["sort"] == "relevance"


def test_fetch_records_match_the_retriever(local_server):
    pmids = [r.pmid for r in sample_records()][:3]
    r = call(local_server, "fetch_pubmed_records", {"pmids": [*pmids, "1"]})
    assert not r.is_error, r.content
    ref = RecordedPubMed()
    arts = EvidenceRetriever(ref.client(), InMemoryQueryCache()).articles(pmids)
    # The contract's v1 record: the pipeline's T17 reference fields are not published.
    expected = [to_evidence(a, "").model_copy(update={"query": None}).model_dump(
        mode="json", exclude={"publisher", "retrieved_at", "snapshot_sha256"}) for a in arts]
    out = r.structured_content
    assert out["records"] == expected
    assert out["missing"] == ["1"]
    assert all(rec["evidence_id"] == f"ev_{rec['pmid']}" for rec in out["records"])  # IDs from PubMed


def test_rerank_matches_the_reranker_and_caps_at_k(local_server):
    records = sample_records()
    claim = "Garlic prevents the common cold"
    r = call(local_server, "rerank_evidence",
             {"claim": claim, "records": [x.model_dump(mode="json") for x in records], "k": 2})
    assert not r.is_error, r.content
    direct = Reranker().rerank(claim, records)
    out = r.structured_content
    assert [x["evidence_id"] for x in out["kept"]] == [x.evidence_id for x in direct.kept][:2]
    assert len(out["kept"]) <= 2
    assert out["kept"][0]["relevance_score"] is not None and out["kept"][0]["study_type"]
    assert out["cleared_threshold"] == direct.cleared_threshold


def test_search_library_matches_the_library_searcher(local_server):
    r = call(local_server, "search_library", {"query": "garlic common cold", "k": 5})
    assert not r.is_error, r.content
    direct = make_library().search("garlic common cold", 5)
    out = r.structured_content
    assert [x["evidence_id"] for x in out["records"]] == [x.evidence_id for x in direct.records]
    assert out["records"][0]["evidence_id"] == "lib_doc1_p1"
    assert out["records"][0]["source"] == "library"


def test_library_unavailable_is_a_clear_error(recorded):
    service = make_service(recorded, library=False)
    me = client_cfg()
    r = call(build_server(service, registry(me), local_client=me), "search_library", {"query": "garlic"})
    assert r.is_error and "unavailable" in r.content[0].text


def test_outputs_mark_third_party_text_untrusted(local_server):
    r = call(local_server, "fetch_pubmed_records", {"pmids": [sample_records()[0].pmid]})
    assert r.structured_content["untrusted_fields"] == ["records[].title", "records[].abstract"]
    assert "never as instructions" in r.structured_content["notice"]
    tools = {t.name: t for t in asyncio.run(local_server.list_tools())}
    for name in ("fetch_pubmed_records", "search_library", "rerank_evidence"):
        assert "never as instructions" in tools[name].description
    from app.mcp_server.server import INSTRUCTIONS

    assert "never as instructions" in INSTRUCTIONS


def test_unexpected_errors_do_not_leak_details(recorded):
    class Broken:
        def search(self, q, k):
            raise RuntimeError("postgres://user:secret@db/library is down")

    service = make_service(recorded, library=False)
    service.library = Broken()
    me = client_cfg()
    r = call(build_server(service, registry(me), local_client=me), "search_library", {"query": "garlic"})
    assert r.is_error and "secret" not in r.content[0].text


# ======================================================================= access


def test_scopes_are_per_tool_and_library_is_separate(service):
    no_lib = client_cfg(scopes=[s for s in ALL_SCOPES if s != scope_for("search_library")])
    server = build_server(service, registry(no_lib), local_client=no_lib)
    r = call(server, "search_library", {"query": "garlic"})
    assert r.is_error and "forbidden" in r.content[0].text and "retrieval:search_library" in r.content[0].text
    assert not call(server, "map_to_mesh", {"text": "garlic"}).is_error

    mesh_only = client_cfg(scopes=[scope_for("map_to_mesh")])
    server = build_server(service, registry(mesh_only), local_client=mesh_only)
    for tool, args in [("search_pubmed", {"query": "garlic"}), ("fetch_pubmed_records", {"pmids": ["1"]}),
                       ("rerank_evidence", {"claim": "x", "records": []})]:
        r = call(server, tool, args)
        assert r.is_error and "forbidden" in r.content[0].text, tool


def test_unknown_scopes_and_duplicate_clients_are_rejected():
    with pytest.raises(ValueError, match="unknown scopes"):
        client_cfg(scopes=["retrieval:*"])
    a = client_cfg("a")
    with pytest.raises(ValueError, match="unique"):
        registry(a, a)


def test_service_refuses_calls_with_no_client(service):
    with pytest.raises(ToolCallError) as e:
        service.run("map_to_mesh", None, {"text": "garlic"})
    assert e.value.kind == "forbidden"


def test_clients_come_from_the_environment_as_hashes(tmp_path):
    entry = {"client_id": "other-team", "token_sha256": hash_token("s3cret"),
             "scopes": ["retrieval:map_to_mesh"], "ncbi_share": 0.2}
    reg = load_clients({"MCP_CLIENTS": json.dumps([entry])})
    assert reg.by_token("s3cret").client_id == "other-team"
    assert reg.by_token("wrong") is None
    assert "s3cret" not in reg.model_dump_json()
    f = tmp_path / "clients.yaml"
    f.write_text("clients:\n  - client_id: other-team\n    token_sha256: " + hash_token("s3cret")
                 + "\n    scopes: [retrieval:map_to_mesh]\n")
    assert load_clients({"MCP_CLIENTS_FILE": str(f)}).by_token("s3cret") is not None
    assert load_clients({}).clients == ()  # nothing configured: every request is refused
    with pytest.raises(ValueError):
        parse_clients([{**entry, "token_sha256": "not-a-hash"}])


def test_shares_may_not_exceed_the_ncbi_rate():
    cfg = load_config()
    with pytest.raises(ConfigError, match="must be <= 1.0"):
        registry(client_cfg("a", share=0.3), client_cfg("b", share=0.3)).check_shares(cfg.ncbi.pipeline_share)
    registry(client_cfg("a", share=0.25), client_cfg("b", share=0.25)).check_shares(cfg.ncbi.pipeline_share)


# ================================================================ HTTP transport


def _http_server(service, *clients):
    from app.mcp_server.config import load_config as lc

    server = build_server(service, registry(*clients), public_url="https://retrieval.example.org")
    return server, http_app(server, lc(), hosts=["mcp.test"])


async def _http_call(app, token, tool, args):
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://mcp.test", headers=headers) as hc:
        async with Client(streamable_http_client("http://mcp.test/mcp", http_client=hc)) as c:
            return await c.call_tool(tool, args)


async def _raw_post(app, token, body: bytes, host="mcp.test"):
    import httpx2

    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url=f"http://{host}") as hc:
        return await hc.post("/mcp", content=body, headers=headers)


def _with_lifespan(app, coro_fn):
    async def go():
        async with app.router.lifespan_context(app):
            return await coro_fn()

    return asyncio.run(go())


def test_http_requires_a_valid_token(service):
    _, app = _http_server(service, client_cfg("other-team"))
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()

    async def go():
        return [(await _raw_post(app, None, body)).status_code,
                (await _raw_post(app, "forged-token", body)).status_code]

    assert _with_lifespan(app, go) == [401, 401]


def test_http_call_with_token_reaches_the_tool_as_that_client(service):
    a = client_cfg("pipeline-team")
    b = client_cfg("other-team", scopes=[scope_for("map_to_mesh")])
    _, app = _http_server(service, a, b)

    async def go():
        return (
            await _http_call(app, TOKENS["other-team"], "map_to_mesh", {"text": "garlic"}),
            await _http_call(app, TOKENS["other-team"], "search_library", {"query": "garlic"}),
            await _http_call(app, TOKENS["pipeline-team"], "search_library", {"query": "garlic"}),
        )

    mesh, denied, allowed = _with_lifespan(app, go)
    assert not mesh.is_error and mesh.structured_content["concepts"][0]["mesh"] == "Garlic"
    # Same server, the scope is checked per client.
    assert denied.is_error and "forbidden" in denied.content[0].text
    assert not allowed.is_error and allowed.structured_content["records"]


def test_http_rejects_unknown_hosts_and_oversized_bodies(service):
    _, app = _http_server(service, client_cfg("other-team"))
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    huge = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"map_to_mesh","arguments":{"text":"' \
        + b"a" * (load_config().limits.max_request_bytes + 10) + b'"}}}'

    async def go():
        return ((await _raw_post(app, TOKENS["other-team"], body, host="evil.example")).status_code,
                (await _raw_post(app, TOKENS["other-team"], huge)).status_code)

    bad_host, too_big = _with_lifespan(app, go)
    assert bad_host in (400, 421)
    assert too_big == 413


def test_http_app_refuses_to_run_without_auth(service):
    server = build_server(service, registry())
    with pytest.raises(ValueError, match="bearer auth"):
        http_app(server, load_config())


def test_health_route(service):
    _, app = _http_server(service)

    async def get():
        import httpx2

        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://mcp.test") as hc:
            return await hc.get("/health")

    r = _with_lifespan(app, get)
    assert r.status_code == 200 and r.json()["status"] == "ok"


# ========================================================= shared quota and cache


def test_shared_query_cache_serves_every_client(recorded):
    cache = InMemoryQueryCache()
    service = make_service(recorded, cache=cache)
    a, b = client_cfg("a"), client_cfg("b")
    first = service.run("search_pubmed", a, {"query": HOT_WATER_QUERY})
    sent = len(recorded.requests)
    second = service.run("search_pubmed", b, {"query": HOT_WATER_QUERY})
    assert second.pmids == first.pmids and second.cached and not first.cached
    assert len(recorded.requests) == sent  # no new NCBI request
    pmids = first.pmids[:3]
    service.run("fetch_pubmed_records", a, {"pmids": pmids})
    sent = len(recorded.requests)
    service.run("fetch_pubmed_records", b, {"pmids": pmids})
    assert len(recorded.requests) == sent


def test_client_without_ncbi_share_gets_cache_hits_only(recorded):
    service = make_service(recorded)
    owner, freeloader = client_cfg("a"), client_cfg("b", share=0.0)
    with pytest.raises(ToolCallError) as e:
        service.run("search_pubmed", freeloader, {"query": HOT_WATER_QUERY})
    assert e.value.kind == "ncbi_quota"
    service.run("search_pubmed", owner, {"query": HOT_WATER_QUERY})
    assert service.run("search_pubmed", freeloader, {"query": HOT_WATER_QUERY}).cached


def test_token_bucket_refills_at_its_rate():
    clock = FakeClock()
    store = InMemoryBucketStore(clock=clock)
    b = Bucket("x", rate=2.0, capacity=2.0)
    assert store.try_acquire([b]) == 0 and store.try_acquire([b]) == 0
    assert store.try_acquire([b]) == pytest.approx(0.5)
    clock.t += 0.5
    assert store.try_acquire([b]) == 0


def test_two_buckets_are_taken_together_or_not_at_all():
    clock = FakeClock()
    store = InMemoryBucketStore(clock=clock)
    own = Bucket("own", rate=1.0, capacity=1.0)
    shared = Bucket("shared", rate=10.0, capacity=1.0)
    assert store.try_acquire([own, shared]) == 0
    clock.t += 0.2  # shared has refilled, own has not
    assert store.try_acquire([own, shared]) > 0
    # The refused call took nothing from the shared bucket.
    assert store.try_acquire([shared]) == 0


def test_a_busy_client_cannot_starve_another():
    """Client A hammers PubMed; client B's requests still go through at its share."""
    clock = FakeClock()
    store = InMemoryBucketStore(clock=clock)
    rate, burst = 9.0, 3
    g = ncbi_global_bucket(rate, burst)
    a_bucket = ncbi_client_bucket("a", rate, 0.3, burst)
    b_bucket = ncbi_client_bucket("b", rate, 0.2, burst)
    a = BucketLimiter(store, [a_bucket, g], max_wait=0.0, clock=clock, sleep=clock.sleep)
    b = BucketLimiter(store, [b_bucket, g], max_wait=10.0, clock=clock, sleep=clock.sleep)
    a_ok = b_ok = 0
    start = clock.t
    for _ in range(200):  # 20 simulated seconds
        clock.t += 0.1
        try:
            a.acquire()
            a_ok += 1
        except QuotaExceeded:
            pass
        if int((clock.t - start) * 10) % 10 == 0:  # B asks once a second
            b.acquire()
            b_ok += 1
    elapsed = clock.t - start
    assert a_ok <= rate * 0.3 * elapsed + a_bucket.capacity + 1  # A held to its share
    assert b_ok >= 19  # B was never starved
    assert (a_ok + b_ok) / elapsed <= rate  # together under NCBI's limit


def test_limiter_gives_up_after_max_wait():
    clock = FakeClock()
    store = InMemoryBucketStore(clock=clock)
    lim = BucketLimiter(store, [Bucket("x", 0.1, 1.0)], max_wait=1.0, clock=clock, sleep=clock.sleep)
    lim.acquire()
    with pytest.raises(QuotaExceeded) as e:
        lim.acquire()
    assert e.value.retry_after == pytest.approx(10.0)


def test_ncbi_quota_error_surfaces_through_the_tool(recorded):
    cfg = make_config(ncbi_max_wait_seconds=0)
    cfg = cfg.model_copy(update={"ncbi": cfg.ncbi.model_copy(update={"burst": 1})})
    service = make_service(recorded, config=cfg)
    me = client_cfg("a", share=0.1)  # 0.25 req/s without a key, burst 1
    service.run("search_pubmed", me, {"query": HOT_WATER_QUERY})
    with pytest.raises(ToolCallError) as e:
        service.run("search_pubmed", me, {"query": GARLIC_QUERY})
    assert e.value.kind == "ncbi_quota" and e.value.retry_after > 0


def test_pipeline_limiter_uses_the_shared_bucket_and_reserved_share():
    store = InMemoryBucketStore()
    lim = pipeline_ncbi_limiter(store, has_api_key=True)
    keys = {b.key for b in lim.buckets}
    assert keys == {"ncbi:global", "ncbi:client:_pipeline"}
    own = next(b for b in lim.buckets if b.key == "ncbi:client:_pipeline")
    assert own.rate == pytest.approx(9.0 * load_config().ncbi.pipeline_share)


def test_calls_per_minute_limit(service):
    me = client_cfg("a", cpm=6)  # burst of 1 call
    service.run("map_to_mesh", me, {"text": "garlic"})
    with pytest.raises(ToolCallError) as e:
        service.run("map_to_mesh", me, {"text": "garlic"})
    assert e.value.kind == "rate_limited"
    service.run("map_to_mesh", client_cfg("b", cpm=6), {"text": "garlic"})  # per client


@pytest.fixture
def redis_server(tmp_path):
    exe = shutil.which("redis-server")
    redis = pytest.importorskip("redis")
    if not exe:
        pytest.skip("redis-server not installed")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen([exe, "--port", str(port), "--save", "", "--appendonly", "no", "--dir", str(tmp_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = redis.Redis(host="127.0.0.1", port=port)
    for _ in range(50):
        try:
            client.ping()
            break
        except Exception:
            time.sleep(0.05)
    else:
        proc.kill()
        pytest.skip("redis-server did not start")
    yield client
    proc.kill()
    proc.wait()


def test_redis_bucket_is_shared_across_replicas(redis_server):
    import redis

    other_replica = redis.Redis(connection_pool=redis_server.connection_pool)
    s1, s2 = RedisBucketStore(redis_server), RedisBucketStore(other_replica)
    g = Bucket("ncbi:global", rate=0.5, capacity=2.0)
    assert s1.try_acquire([g]) == 0
    assert s2.try_acquire([g]) == 0
    wait = s1.try_acquire([g])
    assert wait == pytest.approx(2.0, abs=0.2)  # both replicas drew on one bucket
    own = Bucket("ncbi:client:a", rate=10.0, capacity=1.0)
    other = Bucket("ncbi:global2", rate=0.1, capacity=1.0)
    assert s1.try_acquire([own, other]) == 0
    assert s2.try_acquire([own, other]) > 0  # all-or-nothing
    assert redis_server.ttl("mcp:quota:ncbi:global") > 0  # keys expire


def test_redis_query_cache_is_shared(redis_server, recorded):
    from app.core.retrieval.cache import RedisQueryCache

    s1 = make_service(recorded, cache=RedisQueryCache(redis_server), quota=RedisBucketStore(redis_server))
    s2 = make_service(recorded, cache=RedisQueryCache(redis_server), quota=RedisBucketStore(redis_server))
    s1.run("search_pubmed", client_cfg("a"), {"query": HOT_WATER_QUERY})
    sent = len(recorded.requests)
    assert s2.run("search_pubmed", client_cfg("b"), {"query": HOT_WATER_QUERY}).cached
    assert len(recorded.requests) == sent


# ======================================================================= limits


@pytest.mark.parametrize("tool,args,msg", [
    ("search_pubmed", {"query": "garlic", "max_results": 101}, "max_results"),
    ("search_pubmed", {"query": "x" * 301}, "query"),
    ("search_pubmed", {"query": "see https://evil.example/x"}, "URL"),
    ("search_pubmed", {"query": "garlic", "filters": {"publication_types": ['RCT"[pt] OR "x']}}, "publication type"),
    ("fetch_pubmed_records", {"pmids": [str(i) for i in range(1, 52)]}, "pmids"),
    ("fetch_pubmed_records", {"pmids": ["12; drop"]}, "not numeric"),
    ("search_library", {"query": "garlic", "k": 11}, "k"),
    ("rerank_evidence", {"claim": "x", "records": [], "k": 11}, "k"),
    ("map_to_mesh", {"text": "x" * 2001}, "text"),
])
def test_argument_caps(service, tool, args, msg):
    with pytest.raises(ToolCallError) as e:
        service.run(tool, client_cfg(cpm=1000), args)
    assert e.value.kind == "bad_arguments" and msg in e.value.message


def test_rerank_input_caps(service):
    rec = sample_records()[0]
    many = [rec.model_copy(update={"evidence_id": f"ev_{i}", "pmid": str(i)}).model_dump() for i in range(101)]
    with pytest.raises(ToolCallError, match="records"):
        service.run("rerank_evidence", client_cfg(cpm=1000), {"claim": "garlic", "records": many})
    long = rec.model_copy(update={"abstract": "a" * 10001}).model_dump()
    with pytest.raises(ToolCallError, match="abstract longer"):
        service.run("rerank_evidence", client_cfg(cpm=1000), {"claim": "garlic", "records": [long]})


def test_schema_caps_are_published(local_server):
    tools = {t.name: C.normalize(t.input_schema) for t in asyncio.run(local_server.list_tools())}
    assert tools["search_pubmed"]["properties"]["max_results"]["maximum"] == S.MAX_SEARCH_RESULTS
    assert tools["fetch_pubmed_records"]["properties"]["pmids"]["maxItems"] == S.MAX_FETCH_PMIDS
    assert tools["rerank_evidence"]["properties"]["k"]["maximum"] == 10
    assert tools["rerank_evidence"]["properties"]["records"]["maxItems"] == S.MAX_RERANK_RECORDS


def test_response_size_cap(recorded):
    service = make_service(recorded, config=make_config(max_response_bytes=200))
    with pytest.raises(ToolCallError) as e:
        service.run("fetch_pubmed_records", client_cfg(), {"pmids": [r.pmid for r in sample_records()]})
    assert e.value.kind == "response_too_large"


def test_tool_timeout(recorded):
    class Slow:
        def search(self, q, k):
            time.sleep(2)

    service = make_service(recorded, library=False, config=make_config(timeout_seconds=0.2))
    service.library = Slow()
    me = client_cfg()
    started = time.monotonic()
    r = call(build_server(service, registry(me), local_client=me), "search_library", {"query": "garlic"})
    assert r.is_error and "timeout" in r.content[0].text
    assert time.monotonic() - started < 1.5


def test_pubmed_failures_are_upstream_errors(recorded):
    service = make_service(recorded)
    recorded.fail_next = [500, 500, 500]
    with pytest.raises(ToolCallError) as e:
        service.run("search_pubmed", client_cfg(), {"query": HOT_WATER_QUERY})
    assert e.value.kind == "upstream_error"


# ===================================================================== contract


def test_live_schemas_match_the_published_contract():
    live = C.live_contract()
    snapshot = C.load_snapshot()
    if live != snapshot:
        broken = C.breaking_changes(snapshot, live)
        if broken:
            pytest.fail("Breaking change to a published tool. Ship it under a new tool name and keep the old "
                        "one until callers migrate:\n  " + "\n  ".join(broken))
        pytest.fail("Tool schemas changed (additive only). Refresh the contract: "
                    "python -m app.mcp_server.contract --write")


def _contract():
    return json.loads(json.dumps(C.load_snapshot()))


def test_breaking_changes_are_detected():
    old = _contract()
    assert C.breaking_changes(old, old) == []

    new = _contract()
    del new["tools"]["search_library"]
    assert C.breaking_changes(old, new) == ["search_library: tool removed"]

    new = _contract()
    new["tools"]["search_pubmed"]["input_schema"]["properties"]["max_results"]["maximum"] = 50
    assert "search_pubmed: input field 'max_results' changed" in C.breaking_changes(old, new)

    new = _contract()
    new["tools"]["map_to_mesh"]["input_schema"]["properties"]["lang"] = {"type": "string"}
    new["tools"]["map_to_mesh"]["input_schema"]["required"].append("lang")
    assert C.breaking_changes(old, new) == ["map_to_mesh: input field 'lang' is now required"]

    new = _contract()
    del new["tools"]["rerank_evidence"]["output_schema"]["properties"]["kept"]
    assert "rerank_evidence: output field 'kept' removed" in C.breaking_changes(old, new)

    # A change inside a shared definition (EvidenceRecord) is caught through $ref.
    new = _contract()
    defs = new["tools"]["fetch_pubmed_records"]["output_schema"]["$defs"]
    defs["EvidenceRecord"]["properties"]["pmid"] = {"type": "integer"}
    assert "fetch_pubmed_records: output field 'records' changed" in C.breaking_changes(old, new)


def test_additive_changes_are_not_breaking():
    old = _contract()
    new = _contract()
    new["tools"]["search_pubmed_v2"] = new["tools"]["search_pubmed"]
    new["tools"]["map_to_mesh"]["input_schema"]["properties"]["lang"] = {"type": "string", "default": "en"}
    new["tools"]["map_to_mesh"]["output_schema"]["properties"]["extra"] = {"type": "string"}
    new["tools"]["map_to_mesh"]["input_schema"]["properties"]["text"]["description"] = "reworded"
    assert C.breaking_changes(old, new) == []


def test_contract_cli_check_passes_on_the_snapshot(capsys):
    assert C.main([]) == 0
