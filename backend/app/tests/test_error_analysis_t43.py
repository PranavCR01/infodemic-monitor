"""T43 error analysis: matchers, bootstrap CIs, extraction categories, gold diff,
blind ceiling and the per-item analysis. Synthetic fixtures; no model calls; the
test split (fixture video v04) is never read."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.evaluation.error_analysis import bootstrap as bs
from app.evaluation.error_analysis import cli
from app.evaluation.error_analysis import extraction as ext
from app.evaluation.error_analysis import matching as mt
from app.evaluation.error_analysis.analyze import analyze, step_scores
from app.evaluation.error_analysis.goldset import blind_ceiling, gold_diff
from app.evaluation.routing_experiment.golden import DirSource, TuneSet
from app.tests.test_routing_experiment import GOLDEN, TEST_VIDEO, SpySource


# ------------------------------------------------------------------ matching


def test_strict_matcher_is_t38s_and_rejects_a_faithful_paraphrase():
    gold = ["Turmeric cures cancer"]
    pred = ["the speaker says turmeric can cure cancer"]
    assert mt.strict_match(gold, pred) == []
    assert mt.strict_match(gold, ["turmeric cures cancer"])[0][:2] == (0, 0)
    pairs = mt.meaning_match(gold, pred)
    assert [(g, p) for g, p, _ in pairs] == [(0, 0)]


def test_meaning_matcher_rules():
    assert mt.content_tokens("The cures, cured and curing of Diabétes") == {"cur", "diabet"}
    assert mt.content_tokens("cure") == mt.content_tokens("cures") == mt.content_tokens("curing")
    # One shared word is never enough, however short the claim.
    assert mt.overlap_coefficient("vitamin pills", "vitamin D prevents rickets") == 0.0
    # Below 0.6 needs overlapping time spans.
    g, p = "garlic prevents colds in winter months daily", "garlic prevents flu and other infections"
    s = mt.overlap_coefficient(g, p)
    assert 0.34 <= s < 0.6
    assert mt.meaning_match([g], [p]) == []
    assert mt.meaning_match([g], [p], [(10.0, 12.0)], [(14.0, 15.0)])  # within 3 s
    assert mt.meaning_match([g], [p], [(10.0, 12.0)], [(30.0, 31.0)]) == []
    # One-to-one.
    assert len(mt.meaning_match(["garlic prevents colds"], ["garlic prevents colds", "garlic prevents colds!"])) == 1


# ------------------------------------------------------------------ bootstrap


def test_bootstrap_ci_is_deterministic_and_brackets_the_point():
    vals = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1]
    metric = lambda idx: sum(vals[i] for i in idx) / len(idx)  # noqa: E731
    a = bs.bootstrap_ci(len(vals), metric, n=500)
    b = bs.bootstrap_ci(len(vals), metric, n=500)
    assert a == b and a["point"] == 0.7
    assert a["lo"] < 0.7 < a["hi"] and 0.3 <= a["lo"] and a["hi"] <= 1.0


def test_paired_margin_ci_reflects_how_often_the_ranking_flips():
    better = [1] * 18 + [0] * 2
    worse = [1] * 10 + [0] * 10
    acc = lambda v: (lambda idx: sum(v[i] for i in idx) / len(idx))  # noqa: E731
    clear = bs.paired_margin_ci(20, acc(better), acc(worse), n=500)
    assert clear["point"] == pytest.approx(0.4) and clear["lo"] > 0 and clear["share_not_ahead"] == 0.0
    same = bs.paired_margin_ci(20, acc(better), acc(better), n=200)
    assert same["lo"] == same["hi"] == 0.0 and same["share_not_ahead"] == 1.0


def test_percentile_interpolates():
    assert bs.percentile([0.0, 1.0], 0.5) == 0.5
    with pytest.raises(ValueError):
        bs.percentile([], 0.5)


# ------------------------------------------------------------------ extraction categories


def test_every_unmatched_claim_gets_exactly_one_category():
    gold = [
        ext.Claim("Garlic prevents colds", source="speech"),                       # strict match
        ext.Claim("the speaker says turmeric can cure cancer", source="speech"),   # reworded
        ext.Claim("ginger and honey heal sore throats", source="speech"),          # split into two
        ext.Claim("SEA MOSS CURES THYROID ISSUES", source="screen"),               # screen-only missed
        ext.Claim("cold showers boost immunity", source="speech"),                 # missed
    ]
    pred = [
        ext.Claim("Garlic prevents colds"),
        ext.Claim("Turmeric cures cancer"),
        ext.Claim("ginger heals sore throats"),
        ext.Claim("honey heals sore throats"),
        ext.Claim("aliens built the pyramids with crystal energy"),               # not in the video
        ext.Claim("FOLLOW FOR DAILY DETOX TIPS", source_segment_ids=("o3",)),      # from captions only
        ext.Claim("eat breakfast every single morning"),                           # grounded extra
        ext.Claim("el ajo previene los resfriados y la gripe"),                    # translated
    ]
    transcript = ("Garlic prevents colds. Turmeric cures cancer, trust me. Ginger and honey heal sore throats. "
                  "Cold showers boost immunity. Eat breakfast every single morning.")
    screen = "SEA MOSS CURES THYROID ISSUES  FOLLOW FOR DAILY DETOX TIPS"
    ve = ext.categorise("v", gold, pred, transcript_text=transcript, screen_text=screen)
    assert [g for g, _, _ in ve.strict_pairs] == [0]
    assert ve.gold == {1: "reworded_same_meaning", 2: "split_or_merged", 3: "screen_only_missed", 4: "missed"}
    assert ve.pred == {1: "reworded_same_meaning", 2: "split_or_merged", 3: "split_or_merged",
                       4: "hallucinated", 5: "ocr_noise_derived", 6: "non_health_or_not_a_claim",
                       7: "translated"}
    s = ext.summarise([ve])
    assert s["strict"]["matched"] == 1 and s["meaning"]["matched"] >= 2
    assert sum(s["unmatched_gold"].values()) == 4 and sum(s["unmatched_pred"].values()) == 7


def test_language_guess():
    assert ext.guess_lang("स्तेज फोर कंसर") == "non_latin"
    assert ext.guess_lang("el ajo es bueno para los resfriados") == "es"
    assert ext.guess_lang("the garlic is good for you") == "en"
    assert ext.different_language("en", "non_latin") and not ext.different_language("latin", "es")


# ------------------------------------------------------------------ golden set side


def _golden_copy(tmp_path: Path) -> Path:
    d = tmp_path / "golden_new"
    shutil.copytree(GOLDEN, d)
    rows = (d / "claims.csv").read_text().splitlines()
    out = []
    for r in rows:
        if r.startswith("v02,c2,"):
            r = r.replace(",ENDORSES,SUPPORTED,", ",ENDORSES,MIXED,")  # verdict change
        if r.startswith("v01,c1,"):
            r = r.replace("Hot water every morning cures the flu", "[Hot water] every morning cures the flu")
        out.append(r)
    out.append("v02,c3,Garlic kills the flu virus,speech,research_question,4.0,6.0,REFUTES,CONTRADICTED,,,"
               "fixture,high,pending,,,Added.")
    (d / "claims.csv").write_text("\n".join(out) + "\n")
    (d / "blind").mkdir()
    (d / "blind" / "model_relabel_claims.csv").write_text(
        "video_id,claim_id,claim_text,claim_source,claim_kind,start_seconds,end_seconds,speaker_stance,"
        "claim_verdict\n"
        "v01,c1,Hot water cures the flu,both,research_question,0.0,4.0,ENDORSES,CONTRADICTED\n"
        "v02,c1,the speaker says that garlic can prevent colds,speech,research_question,0.0,3.0,REFUTES,INSUFFICIENT_EVIDENCE\n"
        f"{TEST_VIDEO},c1,Green tea cures cancer,speech,research_question,0.0,3.0,ENDORSES,UNSUPPORTED\n")
    return d


def test_gold_diff_maps_changes_to_items_and_never_reads_the_test_split(tmp_path):
    old = TuneSet(SpySource(GOLDEN))
    new_src = SpySource(_golden_copy(tmp_path))
    d = gold_diff(old, TuneSet(new_src))
    changed = {c["key"]: c["changed"] for c in d["claims"]}
    assert changed == {"v01:c1": ["text"], "v02:c2": ["verdict"], "v02:c3": ["added"]}
    assert d["items_touched"] == {"extract_claims": ["v01", "v02"],
                                  "analyze_stance": ["v01:c1", "v02:c3"],
                                  "verify_claims": ["v01:c1", "v02:c2", "v02:c3"]}
    assert d["transcript_changed"] == [] and d["left_tune"] == d["joined_tune"] == []
    for src in (old.source, new_src):
        assert f"transcripts/{TEST_VIDEO}.json" not in src.reads


def test_blind_ceiling_filters_test_rows_and_scores_both_matchers(tmp_path):
    t = TuneSet(SpySource(_golden_copy(tmp_path)))
    c = blind_ceiling(TuneSet(DirSource(GOLDEN)), t)
    assert c["videos"] == 2 and c["first_claims"] == 3 and c["second_claims"] == 2  # v04 row dropped
    assert c["strict"]["matched"] == 1          # "Hot water cures the flu" ~ gold v01:c1 (Jaccard 5/6)
    assert c["meaning"]["matched"] == 2         # + the "people say ..." paraphrase
    assert f"transcripts/{TEST_VIDEO}.json" not in t.source.reads


# ------------------------------------------------------------------ per-item analysis


def _per_item():
    ext_a = [{"item_id": "v01", "output": [{"text": "Hot water every morning cures the flu", "start": 0.0,
                                            "end": 4.0, "source_segment_ids": ["t1", "o1"]}]},
             {"item_id": "v02", "output": [{"text": "Garlic prevents colds"}]}]
    ext_b = [{"item_id": "v01", "output": []}, {"item_id": "v02", "output": None}]
    st = lambda a, b, c: [{"item_id": "v01:c1", "gold": "ENDORSES", "output": a},  # noqa: E731
                          {"item_id": "v02:c1", "gold": "REFUTES", "output": b},
                          {"item_id": "v02:c2", "gold": "ENDORSES", "output": c}]
    ve = lambda a, b, c: [{"item_id": "v01:c1", "gold": "CONTRADICTED", "output": a},  # noqa: E731
                          {"item_id": "v02:c1", "gold": "INSUFFICIENT_EVIDENCE", "output": b},
                          {"item_id": "v02:c2", "gold": "SUPPORTED", "output": c}]
    return {"golden": "fixture", "split": "tune", "steps": {
        "extract_claims": {"a": ext_a, "b": ext_b},
        "analyze_stance": {"good": st("ENDORSES", "REFUTES", "ENDORSES"), "bad": st("ENDORSES", "ENDORSES", "ENDORSES")},
        "verify_claims": {"good": ve("CONTRADICTED", "CONTRADICTED", "SUPPORTED"),
                          "bad": ve("SUPPORTED", "INSUFFICIENT_EVIDENCE", "SUPPORTED")},
    }}


def test_analyze_scores_cis_errors_and_rescore(tmp_path):
    old = TuneSet(SpySource(GOLDEN))
    new = TuneSet(SpySource(_golden_copy(tmp_path)))
    res = analyze(_per_item(), old, rescore_tune=new, n=200)
    e = res["steps"]["extract_claims"]
    assert e["scores"]["winner"] == "a" and e["scores"]["candidates"]["a"]["point"] == pytest.approx(0.8)
    assert e["scores"]["candidates"]["b"]["point"] == 0.0
    assert e["errors"]["a"]["unmatched_gold"]["missed"] == 1
    s = res["steps"]["analyze_stance"]
    assert s["errors"]["bad"]["refutes_errors"][0]["key"] == "v02:c1"
    assert s["errors"]["bad"]["confusion"]["REFUTES"]["ENDORSES"] == 1
    assert s["scores"]["margin"]["point"] > 0
    v = res["steps"]["verify_claims"]
    assert [x["key"] for x in v["errors"]["good"]["insufficient_called_contradicted"]] == ["v02:c1"]
    # Re-score: the added claim v02:c3 has no output and is listed as not run, not guessed.
    assert v["rescore"]["not_run"] == ["v02:c3"] and v["rescore"]["n_items"] == 3
    assert v["rescore_golden"].startswith("dir:")
    assert isinstance(v["winner_changes"], bool)
    for t in (old, new):
        assert f"transcripts/{TEST_VIDEO}.json" not in t.source.reads


def test_candidates_on_different_items_are_not_paired():
    per = _per_item()["steps"]["analyze_stance"]
    per["bad"] = per["bad"][:2]
    with pytest.raises(ValueError, match="different items"):
        step_scores("analyze_stance", per, TuneSet(DirSource(GOLDEN)), n=10)


def test_cli_commands(tmp_path, capsys, monkeypatch):
    new_dir = _golden_copy(tmp_path)
    refs = {"old": GOLDEN, "new": new_dir}
    monkeypatch.setattr(cli, "_tune", lambda ref, base, golden_dir=None: TuneSet(SpySource(refs[ref])))
    p = tmp_path / "per_item.json"
    p.write_text(json.dumps(_per_item()))
    out = tmp_path / "ea.json"
    assert cli.main(["analyze", "--per-item", str(p), "--golden-ref", "old", "--rescore-ref", "new",
                     "--resamples", "50", "--out", str(out)]) == 0
    res = json.loads(out.read_text())
    assert res["steps"]["verify_claims"]["rescore"]["not_run"] == ["v02:c3"]
    assert cli.main(["gold-diff", "--old", "old", "--new", "new"]) == 0
    assert '"v02:c3"' in capsys.readouterr().out
    assert cli.main(["ceiling", "--first", "old", "--blind-ref", "new"]) == 0
    assert json.loads(capsys.readouterr().out)["videos"] == 2


def test_cli_reports_a_bad_ref_without_a_traceback(capsys):
    assert cli.main(["gold-diff", "--old", "no-such-ref-t43", "--new", "no-such-ref-t43"]) == 1
    assert "error:" in capsys.readouterr().err
