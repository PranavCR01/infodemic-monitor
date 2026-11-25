"""Serves the recorded PubMed fixtures through ``httpx.MockTransport`` (no network)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.core.retrieval.pubmed import EFETCH_URL, ESEARCH_URL, PubMedClient, RateLimiter

FIXTURES = Path(__file__).parent / "fixtures" / "pubmed"


class RecordedPubMed:
    """A fake E-utilities server backed by ``fixtures/pubmed``.

    ``fail_next`` queues HTTP status codes (or exceptions) to return before the real
    answer, to exercise retries. Every request is logged in ``requests``.
    """

    def __init__(self, root: Path = FIXTURES) -> None:
        self.root = root
        self.index: dict[str, str] = json.loads((root / "esearch" / "index.json").read_text())
        self.requests: list[httpx.Request] = []
        self.calls: Counter[str] = Counter()
        self.unknown_queries: list[str] = []
        self.fail_next: list[int | Exception | Callable[[], httpx.Response]] = []

    def _empty(self, term: str) -> dict:
        return {"header": {"type": "esearch", "version": "0.3"},
                "esearchresult": {"count": "0", "retmax": "0", "retstart": "0", "idlist": [],
                                  "translationset": [], "querytranslation": term}}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        endpoint = "esearch" if url == ESEARCH_URL else "efetch" if url == EFETCH_URL else url
        self.calls[endpoint] += 1
        if self.fail_next:
            f = self.fail_next.pop(0)
            if isinstance(f, Exception):
                raise f
            if callable(f):
                return f()
            return httpx.Response(f, text="error", request=request)
        params = request.url.params
        if endpoint == "esearch":
            term = params["term"]
            name = self.index.get(term)
            if name is None:
                self.unknown_queries.append(term)
                payload = self._empty(term)
            else:
                payload = json.loads((self.root / "esearch" / name).read_text())
            return httpx.Response(200, json=payload, request=request)
        if endpoint == "efetch":
            parts = []
            for pmid in params["id"].split(","):
                f = self.root / "efetch" / f"{pmid}.xml"
                if f.exists():
                    parts.append(f.read_text())
            body = ('<?xml version="1.0" ?>\n<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, '
                    '1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">\n'
                    "<PubmedArticleSet>\n" + "".join(parts) + "</PubmedArticleSet>\n")
            return httpx.Response(200, text=body, headers={"content-type": "text/xml"}, request=request)
        return httpx.Response(404, request=request)

    def client(self, *, api_key: str = "", sleeps: Optional[list[float]] = None, **kw) -> PubMedClient:
        sleeps = sleeps if sleeps is not None else []
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        limiter = kw.pop("rate_limiter", None) or RateLimiter(1000.0, sleep=sleeps.append)
        return PubMedClient(http, api_key=api_key, rate_limiter=limiter, sleep=sleeps.append, **kw)
