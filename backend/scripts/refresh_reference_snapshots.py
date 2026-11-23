"""Refresh the stored reference snapshots (T19; design §6, context/MULTI_AGENT.md §7p).

Pages in ``config/reference_sources.yaml`` marked ``retrieval: stored`` (CDC first:
www.cdc.gov blocks scripted requests from cloud hosts) are never fetched while a video
is processed. Claims cite the current version in ``data/reference_snapshots/`` by its
snapshot hash. This script adds versions; commit the result through a pull request so
every change to cited text is reviewed.

    cd backend
    python scripts/refresh_reference_snapshots.py                 # fetch every stored page
    python scripts/refresh_reference_snapshots.py --page cdc_child_schedule
    python scripts/refresh_reference_snapshots.py --dry-run       # what would change
    python scripts/refresh_reference_snapshots.py --check         # verify + ages (CI-safe, no network)
    # the publisher refuses the script too: save the page from a browser, then
    python scripts/refresh_reference_snapshots.py --import cdc_child_schedule=~/Downloads/page.html \
        [--retrieved-at 2026-11-23T10:00:00+00:00]
    # roll back to an earlier version
    python scripts/refresh_reference_snapshots.py --set-current cdc_child_schedule=<sha256>

The fetch uses the same allow-listed fetcher as live retrieval (honest User-Agent, no
redirects, size cap). A refused page is reported; nothing tries to look like a browser.
Exit status: 0 when everything asked for succeeded, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.retrieval.references import ReferenceFetcher, StoredSnapshots, load_reference_config  # noqa: E402
from app.core.retrieval.references.refresh import check, import_saved, refresh  # noqa: E402


def _pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected PAGE_ID=VALUE")
    k, v = value.split("=", 1)
    return k.strip(), v.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="reference config (default: config/reference_sources.yaml)")
    ap.add_argument("--archive", help="snapshot archive directory (default: data/reference_snapshots)")
    ap.add_argument("--page", action="append", default=[], help="catalogue page id (repeatable)")
    ap.add_argument("--import", dest="imports", action="append", default=[], type=_pair,
                    metavar="PAGE_ID=FILE", help="add a version from a saved copy (HTML, or .txt)")
    ap.add_argument("--retrieved-at", help="capture time for --import (ISO-8601; default now)")
    ap.add_argument("--set-current", action="append", default=[], type=_pair, metavar="PAGE_ID=SHA256")
    ap.add_argument("--check", action="store_true", help="verify the archive; no network")
    ap.add_argument("--strict", action="store_true", help="with --check, stale snapshots fail too")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    config = load_reference_config(args.config)
    archive = StoredSnapshots(args.archive)
    ok = True

    if args.check:
        report = check(config, archive)
        for line in report.lines:
            print(line)
        for p in report.problems:
            print(f"PROBLEM {p}")
        if report.stale:
            print(f"stale (older than {config.stored_snapshot_max_age_days} days): {', '.join(report.stale)}")
        return 0 if report.ok and not (args.strict and report.stale) else 1

    for page_id, sha in args.set_current:
        v = archive.set_current(page_id, sha)
        print(f"{page_id}: current is now {v.sha256[:12]} (captured {v.retrieved_at})")

    for page_id, path in args.imports:
        out = import_saved(config, archive, page_id, Path(path).expanduser(),
                           retrieved_at=args.retrieved_at, dry_run=args.dry_run)
        print(out.line())
        ok &= out.status != "failed"

    if not args.imports and not args.set_current:
        fetcher = ReferenceFetcher(config)
        try:
            for out in refresh(config, archive, fetcher, args.page or None, dry_run=args.dry_run):
                print(out.line())
                ok &= out.status != "failed"
        finally:
            fetcher.close()

    if not args.dry_run:
        problems = archive.verify()
        for p in problems:
            print(f"PROBLEM {p}")
        ok &= not problems
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
