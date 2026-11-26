"""Crossref metadata lookup for DOIs PubMed doesn't have yet (T50 item i, lead decision
2026-11-26).

One fixed endpoint (``https://api.crossref.org/works/<doi>``), a polite rate (at most
2 requests a second), a generic User-Agent with no personal contact details, a size
cap and a timeout. The DOI is validated by format before it is put in the URL, and the
response is parsed as data only: title, journal, issue date, abstract (JATS tags
stripped), publisher, type. Nothing in it is followed or executed (§15).
"""
from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import quote

CROSSREF_WORKS_URL = "https://api.crossref.org/works/"
USER_AGENT = "infodemic-monitor-retrieval/1.0 (research; no contact)"
MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_RATE_PER_SECOND = 2.0
DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9<>]+$")


def normalize_doi(raw: Any) -> Optional[str]:
    """A DOI in canonical lower-case form, or None if it isn't one. Accepts the
    ``doi:`` and ``https://doi.org/`` prefixes; rejects whitespace, quotes, query
    strings and anything over 200 characters."""
    if not isinstance(raw, str):
        return None
    d = raw.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):].strip()
    d = d.rstrip(".,;")
    if len(d) > 200 or not DOI_RE.match(d) or "<" in d or ">" in d:
        return None
    return d


@dataclass(frozen=True)
class CrossrefWork:
    doi: str
    title: str
    journal: Optional[str]
    year: Optional[int]
    abstract: str
    publisher: Optional[str]
    type: Optional[str]


def _strip_jats(text: str) -> str:
    t = re.sub(r"<[^>]{0,200}>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def parse_work(payload: Any, doi: str) -> Optional[CrossrefWork]:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    msg = payload.get("message")
    if not isinstance(msg, dict):
        return None
    got = normalize_doi(msg.get("DOI"))
    if got != doi:  # the record must be the one asked for
        return None
    title = next((t for t in msg.get("title") or [] if isinstance(t, str) and t.strip()), "")
    if not title:
        return None
    journal = next((t for t in msg.get("container-title") or [] if isinstance(t, str)), None)
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        parts = ((msg.get(k) or {}).get("date-parts") or [[None]])[0]
        if parts and isinstance(parts[0], int):
            year = parts[0]
            break
    return CrossrefWork(doi=doi, title=_strip_jats(title)[:500], journal=_strip_jats(journal or "")[:300] or None,
                        year=year, abstract=_strip_jats(msg.get("abstract") or "")[:6000],
                        publisher=(msg.get("publisher") or None), type=msg.get("type"))


class CrossrefClient:
    """``work(doi)`` → ``CrossrefWork`` or None (not found / not a usable record)."""

    def __init__(self, http: Any = None, *, rate_per_second: float = DEFAULT_RATE_PER_SECOND,
                 timeout: float = 15.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        if http is None:
            import httpx

            http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})
        self._http = http
        self._interval = 1.0 / rate_per_second
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self._last = -1e9
        self.request_count = 0

    def _wait(self) -> None:
        with self._lock:
            wait = self._last + self._interval - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()

    def work(self, raw_doi: str) -> Optional[CrossrefWork]:
        doi = normalize_doi(raw_doi)
        if doi is None:
            return None
        self._wait()
        self.request_count += 1
        resp = self._http.get(CROSSREF_WORKS_URL + quote(doi, safe="/()._;:-"),
                              headers={"User-Agent": USER_AGENT})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        if len(resp.content) > MAX_RESPONSE_BYTES:
            return None
        return parse_work(resp.json(), doi)


__all__ = ["CROSSREF_WORKS_URL", "CrossrefClient", "CrossrefWork", "USER_AGENT", "normalize_doi", "parse_work"]
