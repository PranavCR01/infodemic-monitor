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


# Every difference the cross-check finds on the golden set @ dcf77b0 (adjudicated
# model-assisted re-label, T42; kind → reasons). All are backend-only review reasons; no
# label, misinfo_basis, deciding-claim or review-routing difference. A change to either
# judge that adds, removes or reclassifies a difference fails here on purpose.
EXPECTED_DIFFERENCES = {
    # 20 reasons on 10 videos: weak_evidence:<cid> on a deciding claim the golden judge
    # already sends with its own reason for the same claim (unproven_claim on 9 MISINFO
    # unproven videos, 19 reasons; mixed_evidence:c2 on v65, 1 reason). Was 17 @ 022ac44:
    # the re-label moved MISINFO/unproven from 7 to 9 videos.
    "weak_evidence_covered_by_judge_reason": 20,
    # D4 dropped (2026-11-24): the former weak_evidence_on_non_deciding_claim kind is gone.
    # T42: the golden judge @ dcf77b0 raises nothing_judged too, so the former
    # nothing_judged_not_in_pinned_golden_judge kind (28 @ 022ac44) is gone.
}


# ------------------------------------------------------------------ the fixture


def test_vendored_golden_judge_is_the_branch_file_verbatim():
    data = (FIXTURE_DIR / "judge.py").read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert blob == META["source"]["judge_blob_sha"]


def test_fixture_covers_every_labelled_video():
    assert len(VIDEOS) == 181
    assert sum(len(v.claims) for v in VIDEOS) == 538
    for v in VIDEOS:
        if v.out_of_scope:
            assert not v.claims, v.video_id  # out_of_scope ⇒ no claims
    # dcf77b0 has 13 in-scope videos with no checkable claim (all CANNOT_RECOGNIZE).
    no_claims = [v for v in VIDEOS if not v.out_of_scope and not v.claims]
    assert len(no_claims) == 13
    assert {v.recorded_label for v in no_claims} == {"CANNOT_RECOGNIZE"}


def test_golden_judge_reproduces_the_recorded_columns(results):
    """The golden set derives video_level_label and review_reasons with its judge, so
    running it on the fixture must give back exactly what videos.csv records."""
    assert [r.video_id for r in results if not r.recorded_reasons_match_golden] == []


# ------------------------------------------------------------------ agreement


def test_same_video_label_on_every_video(results):
    bad = [(r.video_id, r.backend.label, r.golden.label) for r in results if not r.label_agrees]
    assert bad == []


def test_same_misinfo_basis_on_every_video(results):
    """T30: the basis (contradicted / denies_supported / unproven) agrees too."""
    bad = [(r.video_id, r.backend.basis, r.golden.basis) for r in results if not r.basis_agrees]
    assert bad == []  # the recorded basis is checked by the golden-reproduces test


def test_misinfo_counts_by_basis(results):
    counts = Counter(r.backend.basis for r in results if r.backend.label == "MISINFO")
    assert dict(counts) == {"contradicted": 26, "unproven": 9, "denies_supported": 1}


def test_recorded_labels_in_scope():
    """The adjudicated golden set @ dcf77b0 (T42)."""
    counts = Counter(v.recorded_label for v in VIDEOS if not v.out_of_scope)
    assert dict(counts) == {"NO_MISINFO": 48, "CANNOT_RECOGNIZE": 61, "MISINFO": 36, "DEBUNKING": 17}


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
    assert golden_only == set()  # none at dcf77b0


def test_every_difference_kind_says_which_side_matches_section_9():
    for kind, d in xc.DIFFERENCE_KINDS.items():
        assert d["matches"] and d["why"], kind
    assert set(EXPECTED_DIFFERENCES) <= set(xc.DIFFERENCE_KINDS)


def test_agreement_table_counts(results):
    table = {name: (agree, total) for name, agree, total in xc.agreement_table(results)}
    assert table["video label (in scope)"] == (162, 162)
    assert table["video label (out_of_scope, no claims)"] == (19, 19)
    assert table["misinfo_basis (in scope)"] == (162, 162)
    assert table["deciding claims"] == (162, 162)
    assert table["golden judge reproduces videos.csv label + basis + review_reasons"] == (181, 181)
    # The 10 inexact videos are the weak_evidence_covered_by_judge_reason ones.
    assert table["review reasons, exact (shared vocabulary)"] == (152, 162)
    # Both judges send the same 69 in-scope videos to review.
    assert table["sent to review (shared signals)"] == (162, 162)


def test_report_renders(results):
    md = xc.render_markdown(results, "fixture")
    assert "| video label (in scope) | 162 | 162 |" in md
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
    ([("ENDORSES", "UNSUPPORTED")], "MISINFO"),
    ([("ENDORSES", "UNSUPPORTED"), ("ENDORSES", "CONTRADICTED")], "MISINFO"),
    ([("REFUTES", "SUPPORTED"), ("ENDORSES", "UNSUPPORTED")], "MISINFO"),
    ([("QUOTES", "UNSUPPORTED"), ("REFUTES", "CONTRADICTED")], "DEBUNKING"),
    ([("ENDORSES", "UNSUPPORTED"), ("REFUTES", "CONTRADICTED")], "MISINFO"),
])
def test_each_section_9_rule_gives_the_same_label(rows, label):
    r = xc.compare(_video(*rows), GOLDEN.judge, GOLDEN.review_reasons)
    assert r.backend.label == r.golden.label == label
    assert r.basis_agrees and r.deciding_agrees


def test_denies_supported_reason_agrees_when_its_rule_decides():
    r = xc.compare(_video(("REFUTES", "SUPPORTED")), GOLDEN.judge, GOLDEN.review_reasons)
    assert r.backend.reasons == r.golden.reasons == {"denies_supported:c1"}


def test_mixed_video_reason_agrees():
    """Both judges raise mixed_video since 022ac44, also for unproven + refuted-false."""
    for first in ("CONTRADICTED", "UNSUPPORTED"):
        r = xc.compare(_video(("ENDORSES", first), ("REFUTES", "CONTRADICTED")),
                       GOLDEN.judge, GOLDEN.review_reasons)
        assert r.label_agrees and "mixed_video" in r.backend.reasons & r.golden.reasons


def test_refuted_unsupported_is_a_known_backend_deviation():
    """T30 deviation (documented): the backend also treats REFUTES + UNSUPPORTED as a
    possible debunk; the golden judge (§9 pseudocode) does not. Not on the golden set."""
    r = xc.compare(_video(("REFUTES", "UNSUPPORTED")), GOLDEN.judge, GOLDEN.review_reasons)
    assert r.label_agrees and r.backend.label == "CANNOT_RECOGNIZE"
    assert r.backend.deciding == ("c1",) and r.golden.deciding == ()
    assert "possible_debunk:c1" in r.backend_only


def test_nothing_judged_is_shared_with_the_pinned_golden_judge(results):
    """T37/T42: the golden judge @ dcf77b0 has the nothing_judged rule, so both sides
    raise it on the same 26 videos (28 @ 022ac44; the re-label changed the claim verdicts
    of the other 2). Every such video is CANNOT_RECOGNIZE with nothing deciding and has
    an INSUFFICIENT_EVIDENCE claim."""
    gained = [r for r in results if "nothing_judged" in r.backend.reasons]
    assert len(gained) == 26
    assert gained == [r for r in results if "nothing_judged" in r.golden.reasons]
    by_id = {v.video_id: v for v in VIDEOS}
    for r in gained:
        assert "nothing_judged" not in r.differences
        assert r.backend.label == r.golden.label == "CANNOT_RECOGNIZE" and r.backend.deciding == ()
        assert any(c.claim_verdict == "INSUFFICIENT_EVIDENCE" for c in by_id[r.video_id].claims)
        assert not r.out_of_scope
        # D4 dropped: with no deciding claim, nothing_judged is what sends the video.
        assert not any(x.startswith("weak_evidence:") for x in r.backend.reasons)
    # No video with no claims, or only NOT_VERIFIABLE claims, gains it.
    for r in results:
        verdicts = {c.claim_verdict for c in by_id[r.video_id].claims}
        if verdicts <= {"NOT_VERIFIABLE"}:
            assert "nothing_judged" not in r.backend.reasons, r.video_id


def test_nothing_judged_agrees_with_the_pinned_golden_judge():
    """The pinned golden judge raises nothing_judged itself (dcf77b0); a golden judge
    without the rule (as before T42) still yields the classified difference kind."""
    r = xc.compare(_video(("NEUTRAL", "INSUFFICIENT_EVIDENCE")), GOLDEN.judge, GOLDEN.review_reasons)
    assert "nothing_judged" in r.backend.reasons & r.golden.reasons
    assert "nothing_judged" not in r.differences

    def golden_reasons_without_rule(rows):
        return [x for x in GOLDEN.review_reasons(rows) if x != "nothing_judged"]

    r = xc.compare(_video(("NEUTRAL", "INSUFFICIENT_EVIDENCE")), GOLDEN.judge, golden_reasons_without_rule)
    assert r.differences["nothing_judged"] == "nothing_judged_not_in_pinned_golden_judge"


def test_not_verifiable_only_video_gains_no_reason():
    r = xc.compare(_video(("ENDORSES", "NOT_VERIFIABLE")), GOLDEN.judge, GOLDEN.review_reasons)
    assert "nothing_judged" not in r.backend.reasons


def test_backend_sends_69_in_scope_videos_to_review(results):
    """T42: on the adjudicated golden set @ dcf77b0 the backend sends 69 of 162 in-scope
    videos to review, the same videos the golden judge sends and videos.csv records."""
    in_scope = [r for r in results if not r.out_of_scope]
    sent = {r.video_id for r in in_scope if r.backend.reasons}
    assert len(sent) == 69
    assert sent == {r.video_id for r in in_scope if r.golden.reasons}
    assert sent == {v.video_id for v in VIDEOS if v.recorded_review_reasons}


def test_weak_evidence_never_names_a_non_deciding_claim(results):
    for r in results:
        for x in r.backend.reasons:
            if x.startswith("weak_evidence:"):
                assert x.split(":", 1)[1] in r.backend.deciding, (r.video_id, x)


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
