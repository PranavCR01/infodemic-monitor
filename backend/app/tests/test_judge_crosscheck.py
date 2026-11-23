"""Judge cross-check against the golden set's independently written judge (T24, §9, §14).

Runs offline: the golden judge (``research/claim-level/dataset/scripts/judge.py`` on
``data/golden-label-set``) is vendored verbatim in ``fixtures/golden_judge/judge.py``
and the claim-level inputs are in ``fixtures/golden_judge/claims.json``. Regenerate both
with ``python scripts/judge_crosscheck.py --write-fixture``. A last test compares the
fixture with the branch when the branch is available locally, and skips otherwise.

No model calls. The golden labels are data under review, not ground truth: these tests
check that two implementations of §9 agree, and pin every known difference with the
side that matches §9.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from app.evaluation import judge_crosscheck as xc

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden_judge"
META = json.loads((FIXTURE_DIR / "claims.json").read_text())
VIDEOS = xc.from_fixture(META["videos"])


def _load_golden():
    spec = importlib.util.spec_from_file_location("golden_set_judge", FIXTURE_DIR / "judge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


GOLDEN = _load_golden()


@pytest.fixture(scope="module")
def results() -> list[xc.VideoComparison]:
    return xc.compare_all(VIDEOS, GOLDEN.judge, GOLDEN.review_reasons)


# Every difference the cross-check found on the golden set @ 45244b0 (kind → reasons).
# All are review reasons; no label or deciding-claim difference. A change to either
# judge that adds, removes or reclassifies a difference fails here on purpose.
EXPECTED_DIFFERENCES = {
    "mixed_evidence": 15,
    "rule_reason_from_non_deciding_claim": 15,
    "trigger_on_non_deciding_claim_when_nothing_decides": 1,
    "weak_evidence_on_non_deciding_claim": 3,
}


# ------------------------------------------------------------------ the fixture


def test_vendored_golden_judge_is_the_branch_file_verbatim():
    data = (FIXTURE_DIR / "judge.py").read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert blob == META["source"]["judge_blob_sha"]


def test_fixture_covers_every_labelled_video():
    assert len(VIDEOS) == 82
    assert sum(len(v.claims) for v in VIDEOS) == 248
    for v in VIDEOS:
        assert v.out_of_scope == (not v.claims), v.video_id  # out_of_scope ⇔ no claims


def test_golden_judge_reproduces_the_recorded_columns(results):
    """The golden set derives video_level_label and review_reasons with its judge, so
    running it on the fixture must give back exactly what videos.csv records."""
    assert [r.video_id for r in results if not r.recorded_reasons_match_golden] == []


# ------------------------------------------------------------------ agreement


def test_same_video_label_on_every_video(results):
    bad = [(r.video_id, r.backend.label, r.golden.label) for r in results if not r.label_agrees]
    assert bad == []


def test_same_deciding_claims_on_every_video(results):
    bad = [(r.video_id, r.backend.deciding, r.golden.deciding) for r in results if not r.deciding_agrees]
    assert bad == []


def test_backend_label_matches_the_recorded_golden_label(results):
    assert [r.video_id for r in results if r.backend.label != r.recorded_label] == []


def test_review_reasons_differ_only_in_known_classified_ways(results):
    kinds = Counter(k for r in results for k in r.differences.values())
    assert "unclassified" not in kinds, [
        (r.video_id, reason) for r in results for reason, k in r.differences.items() if k == "unclassified"
    ]
    assert dict(kinds) == EXPECTED_DIFFERENCES


def test_backend_never_drops_a_review_the_golden_judge_asks_for(results):
    """Whenever the golden judge sends a video to review, the backend does too: the
    backend never drops a review the golden set asks for."""
    assert [r.video_id for r in results if r.golden.reasons and not r.backend.reasons] == []


def test_every_golden_only_reason_is_one_the_backend_reads_differently_from_section_11(results):
    golden_only = {r.differences[x] for r in results for x in r.golden_only}
    assert golden_only <= {"trigger_on_non_deciding_claim_when_nothing_decides"}


def test_every_difference_kind_says_which_side_matches_section_9():
    for kind, d in xc.DIFFERENCE_KINDS.items():
        assert d["matches"] and d["why"], kind
    assert set(EXPECTED_DIFFERENCES) <= set(xc.DIFFERENCE_KINDS)


def test_agreement_table_counts(results):
    table = {name: (agree, total) for name, agree, total in xc.agreement_table(results)}
    assert table["video label (in scope)"] == (66, 66)
    assert table["video label (out_of_scope, no claims)"] == (16, 16)
    assert table["deciding claims"] == (66, 66)
    assert table["golden judge reproduces videos.csv label + review_reasons"] == (82, 82)
    assert table["review reasons, exact (shared vocabulary)"] == (48, 66)
    assert table["sent to review (shared signals)"] == (52, 66)


def test_report_renders(results):
    md = xc.render_markdown(results, "fixture")
    assert "| video label (in scope) | 66 | 66 |" in md
    assert "UNCLASSIFIED" not in md


# ------------------------------------------------------------------ synthetic cases


def _video(*rows, vid="vx") -> xc.GoldenVideo:
    claims = tuple(
        xc.GoldenClaim(claim_id=f"c{i}", speaker_stance=s, claim_verdict=v,
                       evidence_supporting=("PMID:1",) if v in ("SUPPORTED", "MIXED") else (),
                       evidence_contradicting=("PMID:2",) if v in ("CONTRADICTED", "MIXED") else ())
        for i, (s, v) in enumerate(rows, start=1)
    )
    return xc.GoldenVideo(video_id=vid, out_of_scope=False, recorded_label="", recorded_review_reasons=(),
                          claims=claims)


@pytest.mark.parametrize("rows,label", [
    ([("ENDORSES", "CONTRADICTED")], "MISINFO"),
    ([("REFUTES", "SUPPORTED")], "MISINFO"),
    ([("REFUTES", "CONTRADICTED")], "DEBUNKING"),
    ([("ENDORSES", "SUPPORTED")], "NO_MISINFO"),
    ([("REFUTES", "INSUFFICIENT_EVIDENCE")], "CANNOT_RECOGNIZE"),
    ([("ENDORSES", "NOT_VERIFIABLE")], "CANNOT_RECOGNIZE"),
    ([("ENDORSES", "CONTRADICTED"), ("REFUTES", "CONTRADICTED")], "MISINFO"),
    ([("REFUTES", "SUPPORTED"), ("REFUTES", "CONTRADICTED")], "MISINFO"),
    ([("QUOTES", "CONTRADICTED")], "NO_MISINFO"),
])
def test_each_section_9_rule_gives_the_same_label(rows, label):
    r = xc.compare(_video(*rows), GOLDEN.judge, GOLDEN.review_reasons)
    assert r.backend.label == r.golden.label == label


def test_denies_supported_reason_agrees_when_its_rule_decides():
    r = xc.compare(_video(("REFUTES", "SUPPORTED")), GOLDEN.judge, GOLDEN.review_reasons)
    assert r.backend.reasons == r.golden.reasons == {"denies_supported:c1"}


def test_mixed_video_is_a_backend_only_review_reason():
    """Not on the golden set (no mixed video there yet), so pinned synthetically."""
    r = xc.compare(_video(("ENDORSES", "CONTRADICTED"), ("REFUTES", "CONTRADICTED")),
                   GOLDEN.judge, GOLDEN.review_reasons)
    assert r.label_agrees and r.differences == {"mixed_video": "mixed_video"}


def test_unknown_golden_reason_is_an_error():
    with pytest.raises(xc.UnknownReason):
        xc.normalise_golden_reasons(["a reason nobody wrote"], ["c1"])


# ------------------------------------------------------------------ fixture freshness


def _git_show(path: str) -> str | None:
    ref = f"{META['source']['commit']}:{path}"
    try:
        return subprocess.run(["git", "show", ref], check=True, capture_output=True, text=True,
                              cwd=Path(__file__).parent).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def test_fixture_matches_the_golden_branch_when_available():
    base = META["source"]["judge_path"].rsplit("/scripts/", 1)[0]
    videos_csv, claims_csv = _git_show(f"{base}/videos.csv"), _git_show(f"{base}/claims.csv")
    if videos_csv is None or claims_csv is None:
        pytest.skip("golden-label-set commit not available locally (git fetch origin data/golden-label-set)")
    assert xc.to_fixture(xc.load_golden_csvs(videos_csv, claims_csv)) == META["videos"]
    assert _git_show(META["source"]["judge_path"]) == (FIXTURE_DIR / "judge.py").read_text()
