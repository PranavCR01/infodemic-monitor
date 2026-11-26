"""Production retrieval helpers as the lead set them (2026-11-26, after the T53 paid run).

find_study and crossref are ON: find_study produced every recall gain in
evals/reports/T50/paid_run.md. search_assistant and translate_claims stay OFF: they
changed no claim's outcome. Change config/pipeline.yaml and this test together.
"""
from types import SimpleNamespace

from app.core.inference.providers.graph_provider import retrieval_helpers
from app.core.retrieval.assist import PLAN_SEARCH_STEP, TRANSLATE_STEP
from app.core.retrieval.find_study import FIND_STUDY_STEP
from app.core.routing.config import load_routing
from app.core.routing.mock import MockModelClient
from app.core.routing.router import ModelRouter
from app.core.pipeline_options import DEFAULT_PIPELINE_OPTIONS_PATH, load_pipeline_options


def test_shipped_config_has_find_study_on_and_the_other_helpers_off():
    load_pipeline_options.cache_clear()
    r = load_pipeline_options(DEFAULT_PIPELINE_OPTIONS_PATH).retrieval
    assert (r.search_assistant, r.translate_claims, r.find_study, r.crossref) == (False, False, True, True)


def test_shipped_config_builds_only_the_find_study_step_when_every_step_is_routed():
    load_pipeline_options.cache_clear()
    options = load_pipeline_options(DEFAULT_PIPELINE_OPTIONS_PATH)
    routing = load_routing()
    assert {PLAN_SEARCH_STEP, TRANSLATE_STEP, FIND_STUDY_STEP} <= set(routing.steps)  # all three are routed
    client = MockModelClient(lambda model, request: {})
    router = ModelRouter(routing, {"anthropic": client, "openai": client})
    retriever = SimpleNamespace(client=object())
    planner, find_study = retrieval_helpers(router, retriever, None, options)
    assert planner.assistant is None and planner.translator is None
    assert find_study is not None
    assert find_study.verifier.crossref is not None
