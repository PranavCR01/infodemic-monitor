"""Stored, versioned snapshots for allow-listed pages that refuse scripted requests
(§6 "Pages change, so a snapshot of the fetched text is stored with its hash"; T19).

Some publishers on the allow-list block automated clients: www.cdc.gov answers 403
("Access Denied") to requests from cloud hosts. Their pages are marked
``retrieval: stored`` in ``config/reference_sources.yaml``. At claim time the searcher
never requests them; it reads the *current stored version* from this archive and cites
it by its snapshot hash, exactly like a live page (same ``ref_<hash>`` id formula, same
passage choice, same verdict rules).

The archive is a directory, committed to the repository so every change to cited text
is reviewed in a pull request:

    data/reference_snapshots/
        index.json                       # page id -> url, current hash, version history
        <page_id>/<sha256>.json          # one file per distinct text (immutable)

Versions are never deleted. ``scripts/refresh_reference_snapshots.py`` adds a version
when the publisher's text changes (fetched through the same allow-listed fetcher, or
imported from a copy a person saved in a browser) and can roll ``current`` back to any
earlier hash. Every read re-checks that the text still hashes to its name.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from app.core.retrieval.references.fetcher import FetchedPage, text_sha256

DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "data" / "reference_snapshots"
INDEX = "index.json"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PAGE_ID = re.compile(r"^[a-z0-9_]+$")
Method = Literal["fetched", "imported"]


class StoredSnapshotError(ValueError):
    """The archive is inconsistent: a missing file, or text that doesn't match its hash."""


@dataclass(frozen=True)
class StoredVersion:
    page_id: str
    url: str
    title: str
    sha256: str
    retrieved_at: str  # ISO-8601 UTC: when the publisher's page was captured
    method: str  # "fetched" (refresh script) or "imported" (saved by a person)
    text: str

    def page(self) -> FetchedPage:
        """As a fetched page, so the searcher cites it exactly like a live one."""
        return FetchedPage(url=self.url, title=self.title, text=self.text,
                           sha256=self.sha256, retrieved_at=self.retrieved_at)

    def age_days(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        then = datetime.fromisoformat(self.retrieved_at)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (now - then).total_seconds() / 86_400


@dataclass(frozen=True)
class AddResult:
    version: StoredVersion
    status: Literal["new", "unchanged", "restored"]
    previous_sha256: Optional[str]


def _write_json(path: Path, data: dict) -> None:
    """Atomic write (temp file + rename), stable formatting for readable diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=False)
            fh.write("\n")
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; the image runs as another user
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class StoredSnapshots:
    """Read and extend the archive under ``root``."""

    def __init__(self, root: Optional[Path | str] = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_ROOT

    # ------------------------------------------------------------ index

    def _index(self) -> dict:
        path = self.root / INDEX
        if not path.exists():
            return {"format": 1, "pages": {}}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("pages", {})
        return data

    def page_ids(self) -> list[str]:
        return sorted(self._index()["pages"])

    def history(self, page_id: str) -> list[dict]:
        """``[{sha256, retrieved_at, method}]``, oldest first."""
        entry = self._index()["pages"].get(page_id)
        return list(entry["versions"]) if entry else []

    def current_sha(self, page_id: str) -> Optional[str]:
        entry = self._index()["pages"].get(page_id)
        return entry.get("current") if entry else None

    # ------------------------------------------------------------ versions

    def _path(self, page_id: str, sha256: str) -> Path:
        if not _PAGE_ID.match(page_id) or not _SHA.match(sha256):
            raise StoredSnapshotError(f"bad page id or hash: {page_id!r} {sha256!r}")
        return self.root / page_id / f"{sha256}.json"

    def get(self, page_id: str, sha256: str) -> StoredVersion:
        path = self._path(page_id, sha256)
        if not path.exists():
            raise StoredSnapshotError(f"{page_id}: version {sha256[:12]} is in the index but its file is missing")
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        v = StoredVersion(page_id=d["page_id"], url=d["url"], title=d.get("title", ""),
                          sha256=d["sha256"], retrieved_at=d["retrieved_at"],
                          method=d.get("method", "fetched"), text=d["text"])
        if v.page_id != page_id or v.sha256 != sha256 or text_sha256(v.text) != sha256:
            raise StoredSnapshotError(f"{page_id}: stored text does not match its hash {sha256[:12]}")
        return v

    def current(self, page_id: str) -> Optional[StoredVersion]:
        sha = self.current_sha(page_id)
        return None if sha is None else self.get(page_id, sha)

    def add(self, page_id: str, page: FetchedPage, *, method: Method = "fetched") -> AddResult:
        """Store ``page`` as the current version of ``page_id``. Identical text to the
        current version changes nothing (the capture date stays the first one, which is
        when that text was first seen); text matching an older version makes that
        version current again; anything else is a new version."""
        if text_sha256(page.text) != page.sha256:
            raise StoredSnapshotError(f"{page_id}: text does not match its hash")
        index = self._index()
        entry = index["pages"].get(page_id)
        previous = entry.get("current") if entry else None
        if entry and previous == page.sha256:
            return AddResult(self.get(page_id, previous), "unchanged", previous)
        if entry is None:
            entry = index["pages"][page_id] = {"url": page.url, "current": None, "versions": []}
        if entry["url"] != page.url:
            entry["url"] = page.url  # the catalogue moved the page; history keeps old URLs in the files
        known = {v["sha256"] for v in entry["versions"]}
        status: Literal["new", "restored"] = "restored" if page.sha256 in known else "new"
        if status == "new":
            version = StoredVersion(page_id=page_id, url=page.url, title=page.title, sha256=page.sha256,
                                    retrieved_at=page.retrieved_at, method=method, text=page.text)
            _write_json(self._path(page_id, page.sha256), asdict(version))
            entry["versions"].append({"sha256": page.sha256, "retrieved_at": page.retrieved_at,
                                      "method": method})
        entry["current"] = page.sha256
        index["pages"] = dict(sorted(index["pages"].items()))
        _write_json(self.root / INDEX, index)
        return AddResult(self.get(page_id, page.sha256), status, previous)

    def set_current(self, page_id: str, sha256: str) -> StoredVersion:
        """Roll ``current`` to any stored version (e.g. back after a bad capture)."""
        index = self._index()
        entry = index["pages"].get(page_id)
        if entry is None or sha256 not in {v["sha256"] for v in entry["versions"]}:
            raise StoredSnapshotError(f"{page_id}: no stored version {sha256[:12]}")
        version = self.get(page_id, sha256)
        entry["current"] = sha256
        _write_json(self.root / INDEX, index)
        return version

    def verify(self) -> list[str]:
        """Every problem in the archive (missing files, hash mismatches, a current hash
        outside the history), as messages. Empty means consistent."""
        problems: list[str] = []
        try:
            index = self._index()
        except (OSError, ValueError) as exc:
            return [f"{INDEX}: {exc}"]
        for page_id, entry in index["pages"].items():
            shas = [v.get("sha256", "") for v in entry.get("versions", [])]
            if entry.get("current") not in shas:
                problems.append(f"{page_id}: current version is not in its history")
            for sha in shas:
                try:
                    self.get(page_id, sha)
                except (StoredSnapshotError, OSError, ValueError, KeyError) as exc:
                    problems.append(str(exc))
        return problems
