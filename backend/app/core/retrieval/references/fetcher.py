"""Fetch an allow-listed reference page and turn it into plain text (§6, §15).

``ReferenceFetcher.fetch(url, source)`` refuses any URL outside the source's allow-list
before a request is made: HTTPS only, exact host, path prefix, default port, no
credentials. Redirects are not followed (a redirect off the allow-list would otherwise
be a way out), the response has a timeout and a byte cap, and only text content types
are read. The text is untrusted, like an abstract (§15).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable, Optional

import httpx

from app.core.retrieval.references.config import ReferenceConfig, ReferenceSource, url_allowed

USER_AGENT = "WHO-Infodemic-Monitor/1.0 (research tool; reference fetcher)"
_TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml", "application/xml", "text/xml")


class ReferenceFetchError(RuntimeError):
    """A page could not be fetched. ``kind`` is one of ``not_allowed``, ``http``,
    ``too_large``, ``content_type``, ``empty``."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str
    text: str
    sha256: str  # of ``text`` (UTF-8): the snapshot's hash
    retrieved_at: str  # ISO-8601 UTC

    def to_json(self) -> dict:
        return {"url": self.url, "title": self.title, "text": self.text,
                "sha256": self.sha256, "retrieved_at": self.retrieved_at}

    @classmethod
    def from_json(cls, d: dict) -> "FetchedPage":
        return cls(url=d["url"], title=d.get("title", ""), text=d["text"],
                   sha256=d["sha256"], retrieved_at=d["retrieved_at"])


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ HTML → text

_SKIP = frozenset({"script", "style", "noscript", "template", "svg", "nav", "header", "footer",
                   "form", "button", "iframe", "aside"})
_VOID = frozenset({"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed",
                   "source", "track", "wbr", "param"})
_BLOCK = frozenset({"p", "div", "section", "article", "main", "li", "ul", "ol", "table", "tr", "td",
                    "th", "h1", "h2", "h3", "h4", "h5", "h6", "br", "dd", "dt", "dl", "blockquote",
                    "caption", "figcaption", "pre", "hr", "tbody", "thead"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        if tag in _BLOCK:
            self.parts.append("\n\n" if tag not in ("td", "th", "br") else " \n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if tag in _BLOCK and tag not in _VOID:
            self.parts.append("\n\n" if tag not in ("td", "th") else " ")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """``(title, text)``: visible text with paragraphs separated by blank lines.
    Scripts, styles, navigation, headers and footers are dropped."""
    p = _TextExtractor()
    p.feed(html)
    p.close()
    raw = "".join(p.parts)
    paras = []
    for block in re.split(r"\n\s*\n", raw):
        line = re.sub(r"[ \t\r\f\v]+", " ", block).strip()
        line = re.sub(r"\s*\n\s*", " ", line)
        if line:
            paras.append(line)
    title = re.sub(r"\s+", " ", "".join(p.title_parts)).strip()
    return title, "\n\n".join(paras)


def plain_to_text(text: str) -> str:
    paras = [re.sub(r"\s+", " ", b).strip() for b in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p)


# ------------------------------------------------------------------ fetcher


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReferenceFetcher:
    """GET one allow-listed page. Inject ``http`` (an ``httpx.Client``, e.g. over
    ``httpx.MockTransport`` with recorded pages) in tests."""

    def __init__(self, config: ReferenceConfig, http: Optional[httpx.Client] = None,
                 *, clock: Callable[[], str] = utc_now) -> None:
        self.config = config
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds), follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._clock = clock
        self.request_count = 0

    def check(self, url: str, source: ReferenceSource) -> None:
        if not url_allowed(url, source):
            raise ReferenceFetchError("not_allowed", f"{url!r} is outside source {source.id}'s allow-list")

    def get(self, url: str, source: ReferenceSource, params: Optional[dict] = None) -> httpx.Response:
        """One request under the source's allow-list, size-capped, no redirects."""
        self.check(url, source)
        cap = self.config.max_response_bytes
        self.request_count += 1
        with self._http.stream("GET", url, params=params) as resp:
            if resp.status_code != 200:
                raise ReferenceFetchError("http", f"{url} returned HTTP {resp.status_code}")
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) > cap:
                    raise ReferenceFetchError("too_large", f"{url} exceeded {cap} bytes")
            headers = {k: v for k, v in resp.headers.items()
                       if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
            return httpx.Response(200, headers=headers, content=bytes(buf), request=resp.request)

    def fetch(self, url: str, source: ReferenceSource, *, title: str = "") -> FetchedPage:
        resp = self.get(url, source)
        ctype = resp.headers.get("content-type", "text/html").split(";")[0].strip().lower()
        if ctype not in _TEXT_TYPES:
            raise ReferenceFetchError("content_type", f"{url} returned {ctype!r}")
        if ctype == "text/plain":
            page_title, text = "", plain_to_text(resp.text)
        else:
            page_title, text = html_to_text(resp.text)
        if not text.strip():
            raise ReferenceFetchError("empty", f"{url} had no text")
        return FetchedPage(url=url, title=title or page_title or url, text=text,
                           sha256=text_sha256(text), retrieved_at=self._clock())

    def close(self) -> None:
        self._http.close()
