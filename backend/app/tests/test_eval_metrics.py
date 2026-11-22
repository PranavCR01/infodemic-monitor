"""Metric functions (design doc section 14)."""
import pytest

from app.evaluation import metrics as m


def test_confusion_matrix_and_per_class():
    gold = ["MISINFO", "MISINFO", "DEBUNKING", "NO_MISINFO"]
    pred = ["MISINFO", "NO_MISINFO", "MISINFO", "NO_MISINFO"]
    cm = m.confusion_matrix(gold, pred, m.LABELS)
    assert cm["MISINFO"]["MISINFO"] == 1 and cm["MISINFO"]["NO_MISINFO"] == 1
    assert cm["DEBUNKING"]["MISINFO"] == 1
    prf = m.per_class_prf(gold, pred, m.LABELS)
    assert prf["MISINFO"]["precision"] == pytest.approx(0.5)
    assert prf["MISINFO"]["recall"] == pytest.approx(0.5)
    assert prf["NO_MISINFO"]["precision"] == pytest.approx(0.5)
    assert prf["NO_MISINFO"]["recall"] == 1.0
    assert prf["DEBUNKING"]["recall"] == 0.0
    assert prf["CANNOT_RECOGNIZE"]["support"] == 0


def test_macro_f1_skips_classes_absent_from_gold():
    gold = ["MISINFO", "NO_MISINFO"]
    assert m.macro_f1(gold, gold, m.LABELS) == 1.0
    assert m.macro_f1([], [], m.LABELS) is None


def test_macro_f1_known_value():
    gold = ["a", "a", "b", "b"]
    pred = ["a", "b", "b", "b"]
    # a: P=1 R=.5 F=.667 ; b: P=.667 R=1 F=.8
    assert m.macro_f1(gold, pred, ["a", "b"]) == pytest.approx((2 / 3 + 0.8) / 2)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        m.accuracy(["a"], ["a", "b"])


def test_cohens_kappa():
    assert m.cohens_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    # Textbook example: po=0.7, pe=0.5 -> 0.4
    a = ["y"] * 5 + ["n"] * 5
    b = ["y"] * 4 + ["n"] + ["y"] * 2 + ["n"] * 3
    assert m.cohens_kappa(a, b) == pytest.approx(0.4)
    assert m.cohens_kappa([], []) is None
    assert m.cohens_kappa(["a", "a"], ["a", "a"]) == 1.0


def test_judge_label_rules_in_order():
    assert m.judge_label([("ENDORSES", "CONTRADICTED"), ("REFUTES", "CONTRADICTED")]) == "MISINFO"
    assert m.judge_label([("REFUTES", "CONTRADICTED"), ("ENDORSES", "SUPPORTED")]) == "DEBUNKING"
    assert m.judge_label([("ENDORSES", "SUPPORTED")]) == "NO_MISINFO"
    assert m.judge_label([("ENDORSES", "INSUFFICIENT_EVIDENCE")]) == "CANNOT_RECOGNIZE"
    assert m.judge_label([]) == "CANNOT_RECOGNIZE"


def test_claim_matching_is_one_to_one():
    gold = ["Drinking hot water cures the flu", "Garlic stops colds"]
    pred = ["hot water cures the flu", "garlic stops colds", "garlic stops colds fast"]
    pairs = m.match_claims(gold, pred, threshold=0.5)
    assert [(g, p) for g, p, _ in pairs] == [(0, 0), (1, 1)]
    prf = m.extraction_prf(len(pairs), len(gold), len(pred))
    assert prf["recall"] == 1.0 and prf["precision"] == pytest.approx(2 / 3)


def test_retrieval_metrics():
    assert m.recall_at_k({"1", "2"}, ["1", "3", "2"], k=2) == 0.5
    assert m.ndcg_at_k({"1"}, ["1", "2"], k=5) == 1.0
    assert m.ndcg_at_k({"1"}, ["2", "1"], k=5) == pytest.approx(1 / 1.5849625, rel=1e-6)
    assert m.recall_at_k(set(), ["1"], 5) is None


def test_citation_validity():
    assert m.citation_validity(["ev1", "ev9"], ["ev1", "ev2"]) == (1, 2)


def test_critic_metrics():
    # (verifier wrong, critic intervened)
    out = m.critic_metrics([(True, True), (True, False), (False, True), (False, False)])
    assert out["errors_caught"] == 0.5
    assert out["unnecessary_retry_rate"] == 0.5


def test_calibration():
    assert m.expected_calibration_error([0.9, 0.9], [True, True]) == pytest.approx(0.1)
    assert m.expected_calibration_error([], []) is None
    bins = m.reliability_bins([0.05, 0.95, 1.0], [False, True, True], n_bins=10)
    assert bins[0]["count"] == 1 and bins[9]["count"] == 2 and bins[9]["accuracy"] == 1.0


def test_review_and_operations():
    rv = m.review_metrics([True, False, False, True], [True, None, None, False])
    assert rv["review_share"] == 0.5 and rv["overturn_rate"] == 0.5
    lat = m.latency_summary([100, 200, 300, 400, 1000])
    assert lat["median_ms"] == 300 and lat["p95_ms"] == pytest.approx(880)


def test_wer_and_character_accuracy():
    assert m.word_error_rate("the cat sat", "the cat sat") == 0
    assert m.word_error_rate("the cat sat", "the bat") == pytest.approx(2 / 3)
    assert m.character_accuracy("MYTH", "MYTH") == 1.0
    assert m.character_accuracy("MYTH", "MOTH") == 0.75
    assert m.word_error_rate("", "x") is None
