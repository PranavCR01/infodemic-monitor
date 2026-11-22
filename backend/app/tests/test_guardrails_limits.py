"""Tool and input limits (§15 "Input and tool limits"), enforced in code. No network."""
import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.guardrails import load_guardrails, parse_guardrails
from app.core.guardrails.limits import (
    DailyQuota,
    DuplicateDetector,
    InputRejected,
    RateLimiter,
    cap_claims,
    check_duration,
    check_segments,
    check_transcript,
    sniff_container,
    validate_media,
)
from app.core.guardrails.tools import (
    AsyncGuardedHttpClient,
    GuardedHttpClient,
    ToolGateway,
    ToolLimitError,
    check_url,
)

CFG = load_guardrails()
TOOLS = CFG.tools
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def _limits(**overrides):
    return TOOLS.model_copy(update=overrides)


def _search(rows=None):
    def pubmed_search(query, max_results):
        return (rows if rows is not None else [{"pmid": str(i), "title": f"t{i}"} for i in range(50)])

    return pubmed_search


# ------------------------------------------------------------------- config


def test_config_loads_with_the_expected_limits():
    assert CFG.input.max_claims_per_video == 50
    assert TOOLS.allowed_hosts == ["eutils.ncbi.nlm.nih.gov"]
    assert set(TOOLS.approved) == {"pubmed_search", "pubmed_fetch"}


def test_config_rejects_wildcard_hosts_and_unknown_keys():
    data = CFG.model_dump()
    data["tools"]["allowed_hosts"] = ["*.ncbi.nlm.nih.gov"]
    with pytest.raises(ValueError):
        parse_guardrails(data)
    data = CFG.model_dump()
    data["tools"]["allow_everything"] = True
    with pytest.raises(ValueError):
        parse_guardrails(data)


# -------------------------------------------------------------- tool gateway


def test_only_approved_tools_exist():
    with pytest.raises(ToolLimitError) as e:
        ToolGateway({"shell": lambda **k: []}, TOOLS)
    assert e.value.kind == "unapproved_tool"
    gw = ToolGateway({"pubmed_search": _search()}, TOOLS)
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_fetch", pmids=["1"])  # approved in config but not registered
    assert e.value.kind == "unapproved_tool"
    with pytest.raises(ToolLimitError):
        gw.call("fetch_url", url="https://example.invalid")


@pytest.mark.parametrize("query", [
    "https://evil.example/x", "www.evil.example", "../../etc/passwd", "flu\x00drop", "",
])
def test_queries_are_plain_text(query):
    gw = ToolGateway({"pubmed_search": _search()}, TOOLS)
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query=query)
    assert e.value.kind == "bad_arguments"


def test_unknown_arguments_are_rejected():
    gw = ToolGateway({"pubmed_search": _search()}, TOOLS)
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="flu", host="evil.example")
    assert e.value.kind == "bad_arguments"


def test_query_size_limits():
    gw = ToolGateway({"pubmed_search": _search()}, TOOLS)
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="a" * (TOOLS.max_query_chars + 1))
    assert e.value.kind == "query_too_long"
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query=" ".join(["flu"] * (TOOLS.max_query_terms + 1)))
    assert e.value.kind == "query_too_long"


def test_result_count_is_capped_and_max_results_clamped():
    seen = {}

    def pubmed_search(query, max_results):
        seen["max_results"] = max_results
        return [{"pmid": str(i)} for i in range(100)]

    gw = ToolGateway({"pubmed_search": pubmed_search}, TOOLS)
    rows = gw.call("pubmed_search", query="flu", max_results=500)
    assert seen["max_results"] == TOOLS.max_results
    assert len(rows) == TOOLS.max_results


def test_fetch_ids_must_be_numeric_and_bounded():
    gw = ToolGateway({"pubmed_fetch": lambda pmids: [{"pmid": p} for p in pmids]}, TOOLS)
    assert gw.call("pubmed_fetch", pmids=["1", "1", "2"]) == [{"pmid": "1"}, {"pmid": "2"}]
    with pytest.raises(ToolLimitError):
        gw.call("pubmed_fetch", pmids=["1; DROP TABLE"])
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_fetch", pmids=[str(i) for i in range(TOOLS.max_results + 1)])
    assert e.value.kind == "too_many_ids"


def test_call_budget_per_run():
    gw = ToolGateway({"pubmed_search": _search([])}, _limits(max_calls_per_run=2))
    gw.call("pubmed_search", query="a")
    gw.call("pubmed_search", query="b")
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="c")
    assert e.value.kind == "call_budget"


def test_slow_tools_time_out():
    def slow(query, max_results):
        time.sleep(1.0)
        return []

    gw = ToolGateway({"pubmed_search": slow}, _limits(timeout_seconds=0.05))
    start = time.monotonic()
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="flu")
    assert e.value.kind == "timeout"
    assert time.monotonic() - start < 0.5
    gw.close()


def test_oversized_and_malformed_responses_are_refused():
    big = [{"pmid": "1", "abstract": "x" * 5000}]
    gw = ToolGateway({"pubmed_search": _search(big)}, _limits(max_response_bytes=1000))
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="flu")
    assert e.value.kind == "response_too_large"
    gw = ToolGateway({"pubmed_search": lambda query, max_results: "<html>"}, TOOLS)
    with pytest.raises(ToolLimitError) as e:
        gw.call("pubmed_search", query="flu")
    assert e.value.kind == "bad_response"


# ---------------------------------------------------------------- HTTP layer


@pytest.mark.parametrize("url", [
    "http://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    "https://evil.example/entrez/eutils/esearch.fcgi",
    "https://eutils.ncbi.nlm.nih.gov.evil.example/entrez/eutils/x",
    "https://eutils.ncbi.nlm.nih.gov:8443/entrez/eutils/x",
    "https://user:pw@eutils.ncbi.nlm.nih.gov/entrez/eutils/x",
    "https://eutils.ncbi.nlm.nih.gov/admin",
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/../../admin",
    "file:///etc/passwd",
])
def test_outbound_urls_are_restricted(url):
    with pytest.raises(ToolLimitError) as e:
        check_url(url, TOOLS)
    assert e.value.kind == "host_not_allowed"


def test_allowed_url_passes():
    check_url(EUTILS, TOOLS)


def _client(handler, **limits):
    return GuardedHttpClient(_limits(**limits) if limits else TOOLS, transport=httpx.MockTransport(handler))


def test_http_client_returns_the_body():
    c = _client(lambda req: httpx.Response(200, json={"ok": True}))
    resp = c.get(EUTILS, params={"term": "flu"})
    assert resp.json() == {"ok": True}


def test_http_client_refuses_disallowed_hosts_before_sending():
    sent = []
    c = _client(lambda req: sent.append(req) or httpx.Response(200))
    with pytest.raises(ToolLimitError):
        c.get("https://evil.example/entrez/eutils/x")
    assert sent == []


def test_http_client_does_not_follow_redirects():
    c = _client(lambda req: httpx.Response(302, headers={"location": "https://evil.example/"}))
    with pytest.raises(ToolLimitError) as e:
        c.get(EUTILS)
    assert e.value.kind == "redirect_refused"


def test_http_client_caps_the_body():
    c = _client(lambda req: httpx.Response(200, content=b"x" * 5000), max_response_bytes=1000)
    with pytest.raises(ToolLimitError) as e:
        c.get(EUTILS)
    assert e.value.kind == "response_too_large"

    def streamed(req):
        return httpx.Response(200, stream=httpx.ByteStream(b"y" * 5000))

    with pytest.raises(ToolLimitError):
        _client(streamed, max_response_bytes=1000).get(EUTILS)


def test_http_client_times_out():
    def hang(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(ToolLimitError) as e:
        _client(hang).get(EUTILS)
    assert e.value.kind == "timeout"


def test_http_client_uses_the_configured_timeout_and_no_redirects():
    c = GuardedHttpClient(_limits(timeout_seconds=3))
    assert c._client.timeout.read == 3 and c._client.follow_redirects is False
    c.close()


def test_async_http_client_enforces_the_same_limits():
    async def go():
        ok = AsyncGuardedHttpClient(TOOLS, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
        assert (await ok.get(EUTILS)).text == "ok"
        with pytest.raises(ToolLimitError):
            await ok.get("https://evil.example/entrez/eutils/x")
        big = AsyncGuardedHttpClient(_limits(max_response_bytes=10),
                                     transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"z" * 100)))
        with pytest.raises(ToolLimitError):
            await big.get(EUTILS)
        await ok.aclose()
        await big.aclose()

    asyncio.run(go())


# --------------------------------------------------------------- input limits


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


MP4 = _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41") + _box(b"moov", b"\x00" * 16) + _box(b"mdat", b"\x00" * 64)


def test_valid_mp4_passes():
    check = validate_media(MP4, "clip.mp4", CFG.input)
    assert check.container == "mp4" and check.size_bytes == len(MP4) and len(check.sha256) == 64


@pytest.mark.parametrize("content, name, code", [
    (b"", "a.mp4", "empty_file"),
    (b"%PDF-1.7 not a video", "a.mp4", "unsupported_media"),
    (MP4[:-10], "a.mp4", "corrupt_media"),  # cut off mid-transfer
    (_box(b"ftyp", b"isom\x00\x00\x02\x00") + _box(b"mdat", b"\x00" * 8), "a.mp4", "corrupt_media"),  # no moov
    (MP4, "a.webm", "media_mismatch"),
])
def test_bad_uploads_are_rejected(content, name, code):
    with pytest.raises(InputRejected) as e:
        validate_media(content, name, CFG.input)
    assert e.value.code == code


def test_oversized_upload_is_rejected():
    lim = CFG.input.model_copy(update={"max_file_bytes": 10})
    with pytest.raises(InputRejected) as e:
        validate_media(MP4, "a.mp4", lim)
    assert e.value.code == "file_too_large"


def test_container_sniffing():
    assert sniff_container(b"\x1a\x45\xdf\xa3\x01\x00webm") == "webm"
    assert sniff_container(b"\x1a\x45\xdf\xa3\x01\x00matroska") == "mkv"
    assert sniff_container(b"\x00\x00\x00\x14ftypqt  ") == "mov"
    assert sniff_container(b"GIF89a") is None


@pytest.mark.parametrize("seconds, code", [(None, "corrupt_media"), (float("nan"), "corrupt_media"),
                                           (0.2, "too_short"), (601, "too_long")])
def test_duration_limits(seconds, code):
    with pytest.raises(InputRejected) as e:
        check_duration(seconds, CFG.input)
    assert e.value.code == code
    assert check_duration(30, CFG.input) == 30


def test_duplicate_detection_uses_memory_then_the_database():
    db = {"aaa": "video-1"}
    d = DuplicateDetector(lookup=db.get)
    assert d.check("aaa", "video-9") == "video-1"
    assert d.check("bbb", "video-2") is None
    assert d.check("bbb", "video-3") == "video-2"


def test_rate_limit_sliding_window():
    now = [0.0]
    rl = RateLimiter(2, 60, clock=lambda: now[0])
    rl.hit("u1")
    rl.hit("u1")
    rl.hit("u2")  # per user
    with pytest.raises(InputRejected) as e:
        rl.hit("u1")
    assert e.value.code == "rate_limited"
    now[0] = 60.0
    rl.hit("u1")
    assert RateLimiter.from_config(CFG.input).requests == CFG.input.rate_limit.requests


def test_daily_quota_resets_at_utc_midnight():
    day = [datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)]
    q = DailyQuota(2, clock=lambda: day[0])
    assert q.consume("u1") == 1
    assert q.consume("u1") == 0
    with pytest.raises(InputRejected) as e:
        q.consume("u1")
    assert e.value.code == "quota_exceeded"
    day[0] += timedelta(hours=2)
    assert q.consume("u1") == 1


def test_work_caps_per_video():
    kept, dropped = cap_claims(list(range(60)), CFG.input)
    assert len(kept) == 50 and dropped == 10
    assert cap_claims([1, 2], CFG.input) == ([1, 2], 0)
    with pytest.raises(InputRejected):
        check_transcript("x" * (CFG.input.max_transcript_chars + 1), CFG.input)
    with pytest.raises(InputRejected):
        check_segments([0] * (CFG.input.max_segments + 1), CFG.input)
