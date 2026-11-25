"""The real golden label set (research/claim-level/dataset @ 948b1c2) through the
evaluation loader (T46, design doc section 14).

Counts and schema checks only. The test split is reserved for T14: these tests count
it but never predict on it, score it, or read a test-split transcript.
"""
from pathlib import Path

import pytest

from app.evaluation.dataset import (
    CLAIM_KINDS,
    CLAIM_VERDICTS,
    MISINFO_BASES,
    REVIEW_STATUSES,
    SOURCES,
    STANCES,
    dataset_hash,
    load_dataset,
)

GOLDEN = Path(__file__).resolve().parents[3] / "research" / "claim-level" / "dataset"


@pytest.fixture(scope="module")
def golden():
    # Labels only; inputs are built per video below (tune split only).
    return load_dataset(GOLDEN, version="948b1c2", with_inputs=False)


def test_golden_set_is_in_the_repo():
    for name in ("videos.csv", "claims.csv", "reference_citations.csv", "README.md"):
        assert (GOLDEN / name).is_file(), name
    assert (GOLDEN / "transcripts").is_dir()


def test_in_scope_videos_claims_and_splits(golden):
    assert len(golden.videos) == 162
    assert len(golden.excluded) == 19  # out_of_scope: no health content, no claims
    assert all(v.out_of_scope and not v.claims for v in golden.excluded)
    assert not any(v.out_of_scope for v in golden.videos)
    assert len(golden.claims()) == 550
    assert len(golden.split("tune")) == 48
    assert len(golden.split("test")) == 114
    tune = {v.video_id for v in golden.split("tune")}
    test = {v.video_id for v in golden.split("test")}
    assert not tune & test and len(tune | test) == 162  # split by video, every video in one


def test_video_label_and_basis_counts(golden):
    assert golden.label_counts() == {
        "NO_MISINFO": 47, "CANNOT_RECOGNIZE": 59, "MISINFO": 39, "DEBUNKING": 17,
    }
    assert golden.basis_counts() == {"contradicted": 26, "unproven": 12, "denies_supported": 1}
    for v in golden.videos:
        assert (v.misinfo_basis is not None) == (v.label.value == "MISINFO"), v.video_id


def test_claim_vocabularies(golden):
    claims = golden.claims()
    assert {c.verdict for c in claims} <= set(CLAIM_VERDICTS)
    assert {c.stance for c in claims} <= set(STANCES)
    assert {c.kind for c in claims} <= set(CLAIM_KINDS)
    assert {c.source for c in claims} <= set(SOURCES)
    assert {c.review_status for c in claims} <= set(REVIEW_STATUSES)
    assert golden.verdict_counts()["UNSUPPORTED"] == 28
    assert sum(golden.verdict_counts().values()) == 550
    for c in claims:
        assert c.start_seconds is not None and c.end_seconds is not None, c.key
        if c.verdict == "UNSUPPORTED":
            assert not c.evidence and c.stance == "ENDORSES", c.key  # §7, T30
        if c.verdict in ("SUPPORTED", "CONTRADICTED", "MIXED"):
            assert c.evidence, c.key  # judged claims cite what was retrieved


def test_labels_follow_from_claims_under_section_9(golden):
    """video_level_label and misinfo_basis are derived by the golden judge; the eval's
    own §9 implementation (metrics.judge_label, incl. the unproven rule) agrees."""
    assert golden.label_inconsistencies() == []


def test_review_fields_and_reasons(golden):
    assert {v.review_status for v in golden.videos} <= set(REVIEW_STATUSES)
    kinds = {k for v in golden.videos for k in v.review_reason_kinds}
    assert kinds <= {"denies_supported", "unproven_claim", "possible_debunk", "mixed_evidence",
                     "mixed_video", "deciding_insufficient", "evidence_both_sides",
                     "unclear_stance", "nothing_judged"}
    unproven = [v for v in golden.videos if v.misinfo_basis == "unproven"]
    assert all("unproven_claim" in v.review_reason_kinds for v in unproven)
    assert set(MISINFO_BASES) == {"contradicted", "denies_supported", "unproven"}


def test_every_in_scope_video_has_a_transcript(golden):
    missing = [v.video_id for v in golden.videos
               if not (GOLDEN / "transcripts" / f"{v.video_id}.json").is_file()]
    assert missing == []


def test_tune_video_input_is_built_from_its_transcript(golden):
    vid = golden.split("tune")[0].video_id
    fusion = golden.input(vid).fusion
    assert fusion.transcript and fusion.metadata["transcript_segments"]
    assert fusion.combined_content.startswith("[SPEECH]")
    for seg in fusion.metadata["ocr_segments"]:
        assert seg["end"] >= seg["start"]
    with pytest.raises(KeyError):
        golden.input(golden.excluded[0].video_id)  # out of scope: no input


def test_hash_covers_labels_and_transcripts(golden):
    assert golden.hash == dataset_hash(GOLDEN)
    assert len(golden.hash) == 64
