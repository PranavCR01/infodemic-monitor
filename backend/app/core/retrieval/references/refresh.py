"""Refresh and check the stored snapshot archive (T19). Used by
``scripts/refresh_reference_snapshots.py``; kept here so it is tested without a network.

- ``refresh``: fetch each stored page through the same allow-listed fetcher as live
  retrieval (HTTPS, exact host and path, no redirects, size cap, honest User-Agent) and
  add a version when the text changed. A page the publisher refuses is reported as
  failed; nothing is retried with a disguised client.
- ``import_saved``: add a version from a copy of the page a person saved in a browser
  (HTML or plain text). The page must be a catalogue page; its URL comes from the config.
- ``check``: the archive is consistent, every stored page has a current version for its
  catalogue URL, and how old each one is.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from app.core.retrieval.references.config import CataloguePage, ReferenceConfig
from app.core.retrieval.references.fetcher import (
    FetchedPage,
    ReferenceFetcher,
    html_to_text,
    plain_to_text,
    text_sha256,
    utc_now,
)
from app.core.retrieval.references.stored import StoredSnapshots


@dataclass(frozen=True)
class RefreshOutcome:
    page_id: str
    status: str  # new | unchanged | restored | failed
    sha256: Optional[str] = None
    previous_sha256: Optional[str] = None
    chars: int = 0
    error: str = ""

    def line(self) -> str:
        if self.status == "failed":
            return f"{self.page_id}: FAILED {self.error}"
        prev = f" (was {self.previous_sha256[:12]})" if self.previous_sha256 and self.status != "unchanged" else ""
        return f"{self.page_id}: {self.status} {self.sha256[:12]}{prev}, {self.chars} chars"


def select_pages(config: ReferenceConfig, page_ids: Optional[Iterable[str]] = None) -> list[CataloguePage]:
    """The stored pages, or the named catalogue pages (unknown names are an error)."""
    if not page_ids:
        return config.stored_pages()
    out = []
    for pid in page_ids:
        page = config.page(pid)
        if page is None:
            raise KeyError(f"{pid!r} is not a catalogue page in the reference config")
        out.append(page)
    return out


def refresh(config: ReferenceConfig, archive: StoredSnapshots, fetcher: ReferenceFetcher,
            page_ids: Optional[Iterable[str]] = None, *, dry_run: bool = False) -> list[RefreshOutcome]:
    outcomes = []
    for page in select_pages(config, page_ids):
        source = config.source(page.source)
        assert source is not None
        try:
            fetched = fetcher.fetch(page.url, source, title=page.title)
        except Exception as exc:  # noqa: BLE001 - report and carry on with the other pages
            outcomes.append(RefreshOutcome(page.id, "failed", error=f"{type(exc).__name__}: {exc}"[:300]))
            continue
        outcomes.append(_store(archive, page, fetched, "fetched", dry_run))
    return outcomes


def import_saved(config: ReferenceConfig, archive: StoredSnapshots, page_id: str, path: Path | str, *,
                 retrieved_at: Optional[str] = None, dry_run: bool = False) -> RefreshOutcome:
    """A version from a saved copy. ``.txt`` is read as plain text, anything else as
    HTML. ``retrieved_at`` is when the copy was saved (default: now)."""
    page = select_pages(config, [page_id])[0]
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    text = plain_to_text(raw) if str(path).lower().endswith(".txt") else html_to_text(raw)[1]
    if not text.strip():
        return RefreshOutcome(page_id, "failed", error=f"{path} has no text")
    when = retrieved_at or utc_now()
    datetime.fromisoformat(when)  # fail early on a malformed date
    fetched = FetchedPage(url=page.url, title=page.title, text=text, sha256=text_sha256(text), retrieved_at=when)
    return _store(archive, page, fetched, "imported", dry_run)


def _store(archive: StoredSnapshots, page: CataloguePage, fetched: FetchedPage, method: str,
           dry_run: bool) -> RefreshOutcome:
    if dry_run:
        current = archive.current_sha(page.id)
        known = {v["sha256"] for v in archive.history(page.id)}
        status = ("unchanged" if current == fetched.sha256 else "restored" if fetched.sha256 in known else "new")
        return RefreshOutcome(page.id, status, fetched.sha256, current, len(fetched.text))
    res = archive.add(page.id, fetched, method=method)  # type: ignore[arg-type]
    return RefreshOutcome(page.id, res.status, res.version.sha256, res.previous_sha256, len(fetched.text))


@dataclass(frozen=True)
class CheckReport:
    lines: list[str]
    problems: list[str]
    stale: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def check(config: ReferenceConfig, archive: StoredSnapshots, now: Optional[datetime] = None) -> CheckReport:
    now = now or datetime.now(timezone.utc)
    problems = list(archive.verify())
    lines: list[str] = []
    stale: list[str] = []
    for page in config.stored_pages():
        try:
            version = archive.current(page.id)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{page.id}: {exc}")
            continue
        if version is None:
            problems.append(f"{page.id}: no stored snapshot (stored pages are never fetched at claim time)")
            continue
        if version.url != page.url:
            problems.append(f"{page.id}: stored snapshot is of {version.url}, catalogue says {page.url}")
            continue
        age = version.age_days(now)
        n = len(archive.history(page.id))
        flag = ""
        if age > config.stored_snapshot_max_age_days:
            stale.append(page.id)
            flag = "  STALE"
        lines.append(f"{page.id}: {version.sha256[:12]} captured {version.retrieved_at} "
                     f"({int(age)} days, {version.method}), {n} version(s){flag}")
    return CheckReport(lines, problems, stale)
