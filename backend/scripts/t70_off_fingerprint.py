"""T70 (g): with ``routing.CLAIM_CONTEXT`` off, output is byte-identical to before T70.

Prints sha256 fingerprints of a full mocked graph run (no network, scripted models, the
recorded PubMed fixtures) for two inputs: the test suite's two-claim sample, and the v135
production fixture 008c97a3's transcript and on-screen text. Fingerprinted, per input:

- every model request the graph sent (step, prompt version, system prompt, input);
- the final graph state (every field, as JSON);
- the classification result;
- what persistence writes (result, claim rows with search trails, verifications, evidence
  links) and the result API's claim views, read back from an in-memory SQLite database.

Run it in this tree and in a checkout of the base (origin/langgraph-build before T70) and
compare: the script only uses APIs that exist in both.

    python scripts/t70_off_fingerprint.py            # from backend/
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND = Path(os.environ.get("FP_BACKEND") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("GIT_SHA", "0000000")

VOLATILE = {"id", "created_at", "updated_at", "decided_at", "finished_at", "latency_ms", "claim_pk",
            "evidence_pk", "result_id", "review_id", "nonce"}


def canon(obj):
    from pydantic import BaseModel

    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): canon(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0])) if str(k) not in VOLATILE}
    if isinstance(obj, (list, tuple)):
        return [canon(x) for x in obj]
    if hasattr(obj, "value") and not isinstance(obj, (str, int, float)):
        return obj.value
    return obj


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(canon(obj), sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def v135_fusion():
    from app.core.schemas.pipeline import FusionResult

    fx = json.loads((BACKEND / "app/tests/fixtures/prod_008c97a3/benzene_v135.real.json").read_text())
    segs = [{"start": t["start_seconds"], "end": t["end_seconds"], "text": t["text"]} for t in fx["transcript_segments"]]
    text = " ".join(s["text"] for s in segs)
    meta = {"ocr_disabled": True, "transcript_segments": segs}
    return FusionResult(transcript=text, visual_text="", combined_content=f"[AUDIO TRANSCRIPT]\n{text}", metadata=meta)


def run_one(name, fusion):
    import socket

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.tests.test_graph_integration as gi
    from app.db.base import Base
    import app.db.models  # noqa: F401
    from app.db.models.claim import ClaimRow
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.db.models.video import Video
    from app.services import pipeline_result_service as prs
    from app.services import result_view_service as rvs

    def refuse(*a, **k):
        raise AssertionError("network")

    socket.socket.connect = refuse  # no network
    client = gi.ScriptedClient()
    provider = gi.make_provider(client)
    outcome = provider.run(fusion, job_id=f"job-{name}", video_id="vid-1")
    requests = [{"step": q.step, "prompt": q.prompt_version, "system": q.system, "input": q.input}
                for q in client.requests]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id="job-1", video_id="vid-1", status=JobStatus.STARTED))
    db.commit()
    prs.persist_outcome(db, "job-1", fusion, outcome)
    rows = db.query(ClaimRow).order_by(ClaimRow.claim_id).all()
    persisted = [{"claim": {c: getattr(r, c) for c in ("claim_id", "text", "category", "start_seconds",
                                                       "end_seconds", "source_segment_ids", "claim_kind",
                                                       "label", "deciding", "search_trail")},
                  "verification": ({c: getattr(r.verification, c) for c in ("verdict", "explanation", "limitations",
                                                                              "raw_confidence", "revisions",
                                                                              "retrieval_attempts", "model",
                                                                              "prompt_version")}
                                   if r.verification else None),
                  "links": sorted((l.evidence.evidence_id, l.relation, l.rank) for l in r.evidence_links)}
                 for r in rows]
    res = db.query(Result).one()
    result = {c: getattr(res, c) for c in ("label", "confidence", "explanation", "provider", "model_used")}
    views = [v.model_dump(mode="json") for v in rvs.claim_views(db, "job-1")]
    return {
        "requests": sha(requests), "state": sha(outcome.state), "classification": sha(outcome.classification),
        "persisted": sha({"result": result, "claims": persisted}), "api_claim_views": sha(views),
        "n_requests": len(requests), "n_claims": len(rows), "label": outcome.classification.label.value,
    }


def main() -> int:
    import app.tests.test_graph_integration as gi
    from app.core.graph import routing as r

    assert not getattr(r, "CLAIM_CONTEXT", False), "run with the switch off"
    out = {"sample": run_one("sample", gi.fusion()), "v135_008c97a3": run_one("v135", v135_fusion())}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
