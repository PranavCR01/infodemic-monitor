"""Serves the reference fixtures through ``httpx.MockTransport`` (no network).

Live catalogue pages are matched by URL; NCBI Bookshelf answers through E-utilities
(ESearch/EFetch on ``db=pubmed`` with ``booksdocs[filter]``) from recorded replies.
Like production: www.cdc.gov answers 403 and the Bookshelf website a reCAPTCHA page, so
CDC pages come from a stored-snapshot archive built from the synthetic CDC fixtures, and
a test that reaches either site fails loudly (``blocked_requests``). Anything else is a 404.
"""
from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path
from typing import Optional

import httpx

from app.core.retrieval.references import (
    InMemorySnapshotStore,
    ReferenceFetcher,
    ReferenceSearcher,
    StoredSnapshots,
    html_to_text,
    load_reference_config,
    text_sha256,
)
from app.core.retrieval.references.config import ReferenceConfig
from app.core.retrieval.references.fetcher import FetchedPage

FIXTURES = Path(__file__).parent / "fixtures" / "references"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
STORED_AT = "2026-11-20T09:00:00+00:00"

PAGES = {
    "https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much": "fda_caffeine.html",
}
# Stored pages (retrieval: stored) and the synthetic HTML their archive is built from.
STORED = {
    "cdc_child_schedule": "cdc_child_schedule.html",
    "cdc_measles_vaccine": "cdc_measles_vaccine.html",
}
CAPTCHA = "<html><body><h1>reCAPTCHA</h1><p>Please verify you are a human.</p></body></html>"


def build_stored_archive(config: Optional[ReferenceConfig] = None, root: Optional[Path] = None,
                         retrieved_at: str = STORED_AT) -> StoredSnapshots:
    """A stored-snapshot archive holding the synthetic CDC pages (one version each)."""
    config = config or load_reference_config()
    archive = StoredSnapshots(root or tempfile.mkdtemp(prefix="ref-snapshots-"))
    for page_id, name in STORED.items():
        page = config.page(page_id)
        if page is None:
            continue
        _, text = html_to_text((FIXTURES / name).read_text())
        archive.add(page_id, FetchedPage(page.url, page.title, text, text_sha256(text), retrieved_at))
    return archive


class RecordedReferences:
    """A fake set of publisher sites. ``overrides`` maps a URL to a response (or an
    exception) to serve instead of the fixture; ``requests`` logs every URL asked for."""

    def __init__(self, *, books: bool = True) -> None:
        self.requests: list[httpx.Request] = []
        self.calls: Counter[str] = Counter()
        self.overrides: dict[str, object] = {}
        self.books = books

    @property
    def blocked_requests(self) -> list[str]:
        """Requests to sites that refuse scripts in production (must stay empty)."""
        return [str(q.url) for q in self.requests
                if q.url.host == "www.cdc.gov" or str(q.url).startswith("https://www.ncbi.nlm.nih.gov/books/")]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        self.calls[url] += 1
        if url in self.overrides:
            o = self.overrides[url]
            if isinstance(o, Exception):
                raise o
            return o(request) if callable(o) else o  # type: ignore[return-value]
        if url == f"{EUTILS}/esearch.fcgi":
            assert request.url.params["db"] == "pubmed"
            assert request.url.params["term"].endswith(" AND booksdocs[filter]")
            if not self.books:
                return httpx.Response(200, json={"esearchresult": {"idlist": []}}, request=request)
            return httpx.Response(200, text=(FIXTURES / "bookshelf_esearch.json").read_text(),
                                  headers={"content-type": "application/json"}, request=request)
        if url == f"{EUTILS}/efetch.fcgi":
            assert request.url.params["db"] == "pubmed" and request.url.params["retmode"] == "xml"
            return httpx.Response(200, text=(FIXTURES / "bookshelf_efetch.xml").read_text(),
                                  headers={"content-type": "text/xml; charset=UTF-8"}, request=request)
        if request.url.host == "www.cdc.gov":
            return httpx.Response(403, text="Access Denied", request=request)
        if url.startswith("https://www.ncbi.nlm.nih.gov/books/"):
            return httpx.Response(200, text=CAPTCHA, headers={"content-type": "text/html"}, request=request)
        name = PAGES.get(url)
        if name is None:
            return httpx.Response(404, text="not found", request=request)
        return httpx.Response(200, text=(FIXTURES / name).read_text(),
                              headers={"content-type": "text/html; charset=utf-8"}, request=request)

    def http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler), follow_redirects=False)

    def fetcher(self, config: Optional[ReferenceConfig] = None, clock=lambda: "2026-11-22T12:00:00+00:00"):
        return ReferenceFetcher(config or load_reference_config(), self.http(), clock=clock)

    def searcher(self, config: Optional[ReferenceConfig] = None, **kw) -> ReferenceSearcher:
        config = config or load_reference_config()
        kw.setdefault("snapshots", InMemorySnapshotStore())
        kw.setdefault("stored", build_stored_archive(config))
        kw.setdefault("sleep", lambda s: None)
        return ReferenceSearcher(config, self.fetcher(config), **kw)
