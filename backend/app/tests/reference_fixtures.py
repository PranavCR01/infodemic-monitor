"""Serves the synthetic reference fixtures through ``httpx.MockTransport`` (no network).

Pages are matched by URL against ``config/reference_sources.yaml``'s catalogue; the
Bookshelf E-utilities calls and book page come from ``fixtures/references``. Anything
else is a 404, so a test that reaches an unexpected URL fails loudly.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

import httpx

from app.core.retrieval.references import (
    InMemorySnapshotStore,
    ReferenceFetcher,
    ReferenceSearcher,
    load_reference_config,
)
from app.core.retrieval.references.config import ReferenceConfig

FIXTURES = Path(__file__).parent / "fixtures" / "references"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

PAGES = {
    "https://www.cdc.gov/vaccines/hcp/imz-schedules/child-adolescent-age.html": "cdc_child_schedule.html",
    "https://www.cdc.gov/measles/vaccines/index.html": "cdc_measles_vaccine.html",
    "https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much": "fda_caffeine.html",
    "https://www.ncbi.nlm.nih.gov/books/NBK000001/": "NBK000001.html",
}


class RecordedReferences:
    """A fake set of publisher sites. ``overrides`` maps a URL to a response (or an
    exception) to serve instead of the fixture; ``requests`` logs every URL asked for."""

    def __init__(self, *, books: bool = True) -> None:
        self.requests: list[httpx.Request] = []
        self.calls: Counter[str] = Counter()
        self.overrides: dict[str, object] = {}
        self.books = books

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
            assert request.url.params["db"] == "books"
            name = "books_esearch.json" if self.books else None
            if name is None:
                return httpx.Response(200, json={"esearchresult": {"idlist": []}}, request=request)
            return httpx.Response(200, text=(FIXTURES / name).read_text(),
                                  headers={"content-type": "application/json"}, request=request)
        if url == f"{EUTILS}/esummary.fcgi":
            assert request.url.params["db"] == "books"
            return httpx.Response(200, text=(FIXTURES / "books_esummary.json").read_text(),
                                  headers={"content-type": "application/json"}, request=request)
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
        return ReferenceSearcher(config, self.fetcher(config), **kw)
