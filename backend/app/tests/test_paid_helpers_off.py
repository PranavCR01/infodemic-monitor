"""Production ships with the paid T50 retrieval helpers off (lead decision, 2026-11-26).

They stay off until the lead has read the capped paid-run report and turns them on.
When that happens, change config/pipeline.yaml and this test together, in the same PR.
"""
from types import SimpleNamespace

from app.core.inference.providers.graph_provider import retrieval_helpers
from app.core.retrieval.assist import PLAN_SEARCH_STEP, TRANSLATE_STEP
from app.core.retrieval.find_study import FIND_STUDY_STEP
from app.core.pipeline_options import DEFAULT_PIPELINE_OPTIONS_PATH, load_pipeline_options


def test_shipped_config_has_every_paid_retrieval_helper_off():
    load_pipeline_options.cache_clear()
    r = load_pipeline_options(DEFAULT_PIPELINE_OPTIONS_PATH).retrieval
    assert (r.search_assistant, r.translate_claims, r.find_study, r.crossref) == (False, False, False, False)


def test_shipped_config_builds_no_helper_even_when_every_step_is_routed():
    load_pipeline_options.cache_clear()
    options = load_pipeline_options(DEFAULT_PIPELINE_OPTIONS_PATH)
    routed = SimpleNamespace(config=SimpleNamespace(steps={PLAN_SEARCH_STEP: 1, TRANSLATE_STEP: 1, FIND_STUDY_STEP: 1}))
    retriever = SimpleNamespace(client=object())
    planner, find_study = retrieval_helpers(routed, retriever, None, options)
    assert planner.assistant is None and planner.translator is None and find_study is None
