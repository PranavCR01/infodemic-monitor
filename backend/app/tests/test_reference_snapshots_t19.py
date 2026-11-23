"""T19: production reference retrieval (design §6 "Trusted sources beyond PubMed").

- Stored, versioned snapshots for allow-listed pages that block scripted requests (CDC
  first): the archive, the refresh/import/rollback script, the committed CDC snapshots,
  and that claims cite them by snapshot hash without any request.
- Passage choice on real, fragmented publisher text.
- Bookshelf over E-utilities is in ``test_reference_sources.py`` (recorded replies).

No network: fetches go through ``httpx.MockTransport``.
"""
from __future__ import annotations

import json
import os
import socket
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.inference.providers import graph_provider as gp
from app.core.retrieval.references import (
    InMemorySnapshotStore,
    ReferenceFetcher,
    StoredSnapshotError,
    StoredSnapshots,
    best_passage,
    is_reference_evidence_id,
    load_reference_config,
    reference_evidence_id,
    text_sha256,
)
from app.core.retrieval.references.config import ReferenceConfig
from app.core.retrieval.references.fetcher import FetchedPage
from app.core.retrieval.references.passages import _stem, candidate_passages
from app.core.retrieval.references.refresh import check, import_saved, refresh
from app.core.retrieval.references.stored import DEFAULT_ROOT
from app.tests.reference_fixtures import FIXTURES, RecordedReferences, build_stored_archive

CHILD = "cdc_child_schedule"
CHILD_URL = "https://www.cdc.gov/vaccines/hcp/imz-schedules/child-adolescent-age.html"
MMR = "Children only need one dose of the MMR vaccine, at 10 years old."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def cfg() -> ReferenceConfig:
    return load_reference_config()


def _page(text: str, url: str = CHILD_URL, when: str = "2026-11-01T00:00:00+00:00") -> FetchedPage:
    return FetchedPage(url, "Child schedule", text, text_sha256(text), when)


# ================================================================ config


def test_cdc_pages_are_stored_and_the_rest_live(cfg):
    stored = {p.id for p in cfg.stored_pages()}
    assert {"cdc_child_schedule", "cdc_adult_schedule", "cdc_measles_vaccine"} <= stored
    assert all(p.source == "cdc" for p in cfg.stored_pages())
    assert cfg.retrieval(cfg.page("fda_caffeine")) == "live"
    assert cfg.source("ncbi_bookshelf").retrieval == "live"


def test_page_retrieval_overrides_its_source(cfg):
    who = cfg.page("who_measles").model_copy(update={"retrieval": "stored"})
    assert cfg.retrieval(who) == "stored"
    child = cfg.page(CHILD).model_copy(update={"retrieval": "live"})
    assert cfg.retrieval(child) == "live"


def test_a_bookshelf_source_cannot_be_stored(cfg):
    data = cfg.model_dump()
    for s in data["sources"]:
        if s["id"] == "ncbi_bookshelf":
            s["retrieval"] = "stored"
    with pytest.raises(ValueError, match="bookshelf"):
        ReferenceConfig.model_validate(data)


# ================================================================ archive


def test_archive_versions_unchanged_restored_and_rollback(tmp_path):
    a = StoredSnapshots(tmp_path)
    assert a.current(CHILD) is None and a.page_ids() == []
    r1 = a.add(CHILD, _page("Two doses of MMR."))
    assert r1.status == "new" and r1.previous_sha256 is None
    # the same text again changes nothing, and keeps the first capture date
    r2 = a.add(CHILD, _page("Two doses of MMR.", when="2026-11-20T00:00:00+00:00"))
    assert r2.status == "unchanged" and r2.version.retrieved_at == "2026-11-01T00:00:00+00:00"
    r3 = a.add(CHILD, _page("Two doses of MMR, at 12 months and 4 years."))
    assert r3.status == "new" and r3.previous_sha256 == r1.version.sha256
    assert a.current_sha(CHILD) == r3.version.sha256
    # the publisher reverted: the old version becomes current again, no new file
    r4 = a.add(CHILD, _page("Two doses of MMR.", when="2026-11-22T00:00:00+00:00"))
    assert r4.status == "restored" and a.current_sha(CHILD) == r1.version.sha256
    assert [v["sha256"] for v in a.history(CHILD)] == [r1.version.sha256, r3.version.sha256]
    assert len(list((tmp_path / CHILD).glob("*.json"))) == 2
    # explicit rollback/forward
    assert a.set_current(CHILD, r3.version.sha256).text.endswith("4 years.")
    with pytest.raises(StoredSnapshotError):
        a.set_current(CHILD, "f" * 64)
    assert a.verify() == []


def test_archive_files_are_readable_json_named_by_hash(tmp_path):
    a = StoredSnapshots(tmp_path)
    v = a.add(CHILD, _page("Two doses.")).version
    path = tmp_path / CHILD / f"{v.sha256}.json"
    d = json.loads(path.read_text())
    assert d["sha256"] == v.sha256 == text_sha256(d["text"]) and d["url"] == CHILD_URL
    assert d["method"] == "fetched"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["pages"][CHILD]["current"] == v.sha256


def test_archive_refuses_mismatched_text_and_reports_damage(tmp_path):
    a = StoredSnapshots(tmp_path)
    with pytest.raises(StoredSnapshotError):
        a.add(CHILD, FetchedPage(CHILD_URL, "t", "text", "0" * 64, "2026-11-01T00:00:00+00:00"))
    v = a.add(CHILD, _page("Two doses.")).version
    (tmp_path / CHILD / f"{v.sha256}.json").unlink()
    assert any("missing" in p for p in a.verify())
    with pytest.raises(StoredSnapshotError):
        a.current(CHILD)
    with pytest.raises(StoredSnapshotError):
        a.get("../etc", v.sha256)  # ids and hashes are checked before touching the disk


# ================================================================ refresh script logic


class _Sites:
    def __init__(self, pages: dict[str, httpx.Response]):
        self.pages, self.urls = pages, []

    def fetcher(self, cfg):
        def handler(req):
            self.urls.append(str(req.url))
            r = self.pages.get(str(req.url))
            return httpx.Response(r.status_code, content=r.content, headers=r.headers, request=req) if r else \
                httpx.Response(404, request=req)
        return ReferenceFetcher(cfg, httpx.Client(transport=httpx.MockTransport(handler)),
                                clock=lambda: "2026-11-23T10:00:00+00:00")


def _html(name: str) -> httpx.Response:
    return httpx.Response(200, text=(FIXTURES / name).read_text(), headers={"content-type": "text/html"})


def test_refresh_fetches_stored_pages_and_records_failures(cfg, tmp_path):
    sites = _Sites({CHILD_URL: _html("cdc_child_schedule.html"),
                    "https://www.cdc.gov/measles/vaccines/index.html": httpx.Response(403, text="Access Denied")})
    archive = StoredSnapshots(tmp_path)
    out = {o.page_id: o for o in refresh(cfg, archive, sites.fetcher(cfg))}
    assert out[CHILD].status == "new" and "new" in out[CHILD].line()
    assert out["cdc_measles_vaccine"].status == "failed" and "403" in out["cdc_measles_vaccine"].error
    assert out["cdc_adult_schedule"].status == "failed"  # no fixture: 404
    assert archive.current(CHILD).method == "fetched"
    assert archive.current(CHILD).retrieved_at == "2026-11-23T10:00:00+00:00"
    assert archive.current("cdc_measles_vaccine") is None
    # only the stored pages were requested, all on the allow-list
    assert all(u.startswith("https://www.cdc.gov/") for u in sites.urls)
    # a second run with the same text is "unchanged"; --dry-run writes nothing
    again = refresh(cfg, archive, sites.fetcher(cfg), [CHILD])
    assert again[0].status == "unchanged"
    sites.pages[CHILD_URL] = httpx.Response(200, text="<p>Children need 3 doses of MMR.</p>",
                                            headers={"content-type": "text/html"})
    dry = refresh(cfg, archive, sites.fetcher(cfg), [CHILD], dry_run=True)
    assert dry[0].status == "new" and len(archive.history(CHILD)) == 1


def test_refresh_refuses_a_redirect_off_the_page(cfg, tmp_path):
    sites = _Sites({CHILD_URL: httpx.Response(302, headers={"location": "https://evil.example/"})})
    out = refresh(cfg, StoredSnapshots(tmp_path), sites.fetcher(cfg), [CHILD])
    assert out[0].status == "failed" and len(sites.urls) == 1


def test_refresh_rejects_unknown_page_ids(cfg, tmp_path):
    with pytest.raises(KeyError):
        refresh(cfg, StoredSnapshots(tmp_path), _Sites({}).fetcher(cfg), ["not_a_page"])


def test_import_a_page_saved_from_a_browser(cfg, tmp_path):
    archive = StoredSnapshots(tmp_path / "a")
    saved = tmp_path / "saved.html"
    saved.write_text((FIXTURES / "cdc_child_schedule.html").read_text())
    out = import_saved(cfg, archive, CHILD, saved, retrieved_at="2026-11-23T08:00:00+00:00")
    assert out.status == "new"
    v = archive.current(CHILD)
    assert v.method == "imported" and v.url == CHILD_URL and v.retrieved_at == "2026-11-23T08:00:00+00:00"
    assert "<" not in v.text and "first dose at 12 through 15 months" in v.text
    # plain text works too; an empty file fails without touching the archive
    txt = tmp_path / "saved.txt"
    txt.write_text("Children need two doses.\n\nFirst at 12 months.")
    assert import_saved(cfg, archive, CHILD, txt).status == "new"
    (tmp_path / "empty.html").write_text("<html><script>x()</script></html>")
    assert import_saved(cfg, archive, CHILD, tmp_path / "empty.html").status == "failed"
    assert len(archive.history(CHILD)) == 2
    with pytest.raises(ValueError):
        import_saved(cfg, archive, CHILD, txt, retrieved_at="yesterday")


def test_check_reports_missing_stale_and_moved(cfg, tmp_path):
    archive = build_stored_archive(cfg, tmp_path, retrieved_at="2026-01-01T00:00:00+00:00")
    report = check(cfg, archive, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert not report.ok and any("cdc_adult_schedule: no stored snapshot" in p for p in report.problems)
    assert set(report.stale) == {CHILD, "cdc_measles_vaccine"}
    moved = cfg.model_copy(update={"catalogue": tuple(
        p.model_copy(update={"url": "https://www.cdc.gov/x.html"}) if p.id == CHILD else p for p in cfg.catalogue)})
    assert any("catalogue says" in p for p in check(moved, archive).problems)


def test_script_check_on_the_committed_archive_passes():
    main = _script_main()
    assert main(["--check"]) == 0


def test_script_import_set_current_and_check(cfg, tmp_path, capsys):
    main = _script_main()
    root = tmp_path / "archive"
    for pid, name in [(CHILD, "cdc_child_schedule.html"), ("cdc_measles_vaccine", "cdc_measles_vaccine.html"),
                      ("cdc_adult_schedule", "cdc_child_schedule.html")]:
        assert main(["--archive", str(root), "--import", f"{pid}={FIXTURES / name}"]) == 0
    first = StoredSnapshots(root).current_sha(CHILD)
    other = tmp_path / "v2.txt"
    other.write_text("Children need two doses of MMR.")
    assert main(["--archive", str(root), "--import", f"{CHILD}={other}"]) == 0
    assert main(["--archive", str(root), "--set-current", f"{CHILD}={first}"]) == 0
    assert StoredSnapshots(root).current_sha(CHILD) == first
    assert main(["--archive", str(root), "--check"]) == 0
    out = capsys.readouterr().out
    assert "cdc_child_schedule:" in out and "2 version(s)" in out
    assert main(["--archive", str(tmp_path / "empty"), "--check"]) == 1


def _script_main():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "refresh_reference_snapshots.py"
    spec = importlib.util.spec_from_file_location("refresh_reference_snapshots", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


# ================================================================ committed archive


def test_committed_archive_covers_every_stored_page(cfg):
    """Production reads these: each stored catalogue page has a current version, for its
    catalogue URL, whose text matches its hash."""
    archive = StoredSnapshots(DEFAULT_ROOT)
    assert archive.verify() == []
    for page in cfg.stored_pages():
        v = archive.current(page.id)
        assert v is not None, page.id
        assert v.url == page.url and text_sha256(v.text) == v.sha256
        assert datetime.fromisoformat(v.retrieved_at).tzinfo is not None
        assert "Access Denied" not in v.text and len(v.text) > 1000  # a real page, not a block page


def test_committed_cdc_snapshot_is_cited_by_hash_without_a_request(cfg):
    rec = RecordedReferences(books=False)
    snaps = InMemorySnapshotStore()
    found = rec.searcher(cfg, snapshots=snaps, stored=StoredSnapshots(DEFAULT_ROOT)).search(
        "The MMR vaccine is given at 12 months")
    cdc = [x for x in found.records if x.publisher == "CDC"]
    assert cdc and rec.blocked_requests == []
    archive = StoredSnapshots(DEFAULT_ROOT)
    for r in cdc:
        page_id = r.query.split(":", 1)[1].split("@", 1)[0]
        v = archive.current(page_id)
        assert r.snapshot_sha256 == v.sha256 and r.query == f"stored:{page_id}@{v.sha256[:12]}"
        assert r.retrieved_at == v.retrieved_at and r.abstract in v.text
        assert is_reference_evidence_id(r.evidence_id)
        assert r.evidence_id == reference_evidence_id(r.source_url, v.sha256, r.abstract)  # same id rule as T17
        assert snaps.get(v.sha256) is not None  # copied to the snapshot table on use
    measles = next(r for r in cdc if "measles" in r.query)
    assert "2 doses of MMR" in measles.abstract and "12–15 months" in measles.abstract


# ================================================================ passages on real text


@pytest.mark.parametrize("a,b", [("doses", "dose"), ("vaccines", "vaccine"), ("months", "month"),
                                 ("studies", "study"), ("recommended", "recommend"), ("boxes", "box")])
def test_stemmer_matches_plurals_and_verb_endings(a, b):
    assert _stem(a) == _stem(b)


def test_stemmer_leaves_short_and_latin_words():
    assert _stem("virus") == "virus" and _stem("dose") == "dose" and _stem("gas") == "gas"


def test_windows_join_short_paragraphs_and_stay_substrings():
    text = ("Header.\n\nChildren — All children are recommended to have 2 doses of MMR vaccines. "
            "Doses are given at:\n\n12–15 months old\n\n1st dose\n\n4–6 years old\n\n2nd dose\n\nFooter text here.")
    p = best_passage("The MMR vaccine is given at 12 months", text)
    assert p is not None and p.text in text
    assert p.text.startswith("Children") and "12–15 months old" in p.text
    assert "Footer" not in p.text  # a window grows only when it adds claim content
    assert best_passage("The MMR vaccine is given at 12 months", text, window_chars=0).text.startswith("Children")


def test_window_size_is_capped():
    paras = [f"MMR fact {i}." for i in range(20)]
    for c in candidate_passages("\n\n".join(paras), max_chars=1200, window_chars=60):
        assert len(c) <= 60 or "\n\n" not in c
        assert c.count("\n\n") < 6


# ================================================================ wiring


def test_production_searcher_reads_the_committed_archive_and_passes_the_ncbi_key(monkeypatch):
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: None, raising=False)
    s = SimpleNamespace(USE_REFERENCE_SOURCES=True, NCBI_API_KEY="k123")
    searcher = gp.reference_searcher(s)
    assert searcher.api_key == "k123"
    assert Path(searcher.stored.root) == DEFAULT_ROOT
