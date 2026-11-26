"""T60: the optional MedCPT cross-encoder plugs into the reranker's RelevanceModel hook.

No torch, no download: the model call is replaced by fixed logits."""
from app.core.retrieval.cross_encoder import DEFAULT_MODEL, CrossEncoderRelevance
from app.core.retrieval.rerank import DEFAULT_RERANK_CONFIG, Reranker
from app.core.retrieval.schemas import EvidenceRecord


class FixedLogits(CrossEncoderRelevance):
    def __init__(self, logits):
        super().__init__()
        self._fixed = logits

    def logits(self, claim_text, records):
        return list(self._fixed[: len(records)])


def _rec(i, title):
    return EvidenceRecord(evidence_id=f"ev_{i}", source="pubmed", title=title, pmid=str(i))


def test_default_model_and_lazy_import():
    m = CrossEncoderRelevance()
    assert m.model_name == DEFAULT_MODEL == "ncbi/MedCPT-Cross-Encoder"
    assert m._model is None  # nothing loaded until first call


def test_squash_is_monotonic_into_unit_interval():
    vals = [CrossEncoderRelevance.squash(x) for x in (-15.0, -1.0, 0.0, 1.0, 12.0)]
    assert vals == sorted(vals)
    assert 0.0 < vals[0] < 0.001 and vals[2] == 0.5 and 0.999 < vals[-1] < 1.0


def test_reranker_uses_cross_encoder_scores_and_threshold():
    recs = [_rec(1, "Deep brain stimulation for psychiatric diseases: what are the risks?"),
            _rec(2, "Nontraumatic intracranial hemorrhage.")]
    model = FixedLogits([-4.2, 1.1])
    res = Reranker(relevance_model=model).rerank(
        "bleeding in the brain can cause permanent neurological damage or death", recs)
    assert [r.evidence_id for r in res.kept] == ["ev_2"]
    assert res.dropped_below_threshold == ["ev_1"]
    assert DEFAULT_RERANK_CONFIG.min_relevance == 0.4  # T60 kept the lexical default


def test_default_reranker_is_still_lexical():
    assert Reranker().relevance_model is None
