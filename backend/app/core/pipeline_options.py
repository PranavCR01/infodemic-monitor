"""Pipeline input options, loaded from ``backend/config/pipeline.yaml`` (T43).

These switch what a step is *given*, not which model runs it (that is routing).
The only option today is ``extraction.use_ocr``: with ``false``, claim extraction
sees the transcript alone. The flag is read here and applied by wrapping the
extraction node's input (``extraction_input``/``wrap_extract_node``), so the node's
own code never checks it. Default ``true`` keeps live behaviour unchanged.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_PIPELINE_OPTIONS_PATH = Path(__file__).resolve().parents[2] / "config" / "pipeline.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExtractionOptions(_Strict):
    use_ocr: bool = True


class RetrievalOptions(_Strict):
    """T50 (§6). Each model helper also needs its step in config/routing.yaml; with
    either off, retrieval runs on the rules alone for that part."""

    search_assistant: bool = True   # plan_search: structured query when rules fall back to keywords
    translate_claims: bool = True   # translate_claim: non-English claims before planning
    find_study: bool = True         # find_study: web search proposes ids, code verifies them
    crossref: bool = True           # DOI-only studies verified via api.crossref.org (journal_doi)


class PipelineOptions(_Strict):
    version: str = "pipeline_v1"
    extraction: ExtractionOptions = ExtractionOptions()
    retrieval: RetrievalOptions = RetrievalOptions()


DEFAULT_OPTIONS = PipelineOptions()


def parse_pipeline_options(data: Mapping[str, Any] | None) -> PipelineOptions:
    return PipelineOptions.model_validate(dict(data or {}))


@lru_cache(maxsize=4)
def load_pipeline_options(path: str | Path = DEFAULT_PIPELINE_OPTIONS_PATH) -> PipelineOptions:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"pipeline options file not found: {p}")
    return parse_pipeline_options(yaml.safe_load(p.read_text()))


def extraction_input(state: Mapping[str, Any], options: PipelineOptions) -> dict:
    """The state the extraction node should see under ``options``.

    ``use_ocr: true`` returns the state unchanged. ``false`` drops the OCR segments and
    re-fuses the transcript alone, so no caption text (attached or caption-only) reaches
    the extractor. The original state is not modified.
    """
    if options.extraction.use_ocr:
        return dict(state)
    from app.core.graph.nodes import fuse_by_overlap  # local: graph imports are heavy

    transcript = list(state.get("transcript_segments") or [])
    return {**state, "ocr_segments": [], "fused_segments": fuse_by_overlap(transcript, [])}


def wrap_extract_node(node: Callable[[Any], dict], options: PipelineOptions) -> Callable[[Any], dict]:
    """``node`` unchanged when OCR is on; otherwise a node that hands it
    ``extraction_input(state)``. Its update (claims, errors) is returned as is."""
    if options.extraction.use_ocr:
        return node

    def extract_claims_without_ocr(state: Any) -> dict:
        return node(extraction_input(state, options))

    extract_claims_without_ocr.__name__ = getattr(node, "__name__", "extract_claims")
    return extract_claims_without_ocr
