"""§17 read endpoints for results (T26).

- ``GET /v1/videos/{video_id}/results``: final label, explanation, review case, claims,
  segments (the same body as ``GET /jobs/{job_id}/result``) for the video's current
  result: the newest finished job the caller may see (T55), with ``previous_jobs``.
- ``GET /v1/videos/{video_id}/claims``: claims with stance, verdict, critic and papers.
- ``GET /v1/claims/{claim_id}/evidence``: every paper the verifier saw for one claim
  (``claim_id`` is the claim's stable ``id`` from the claims response).

Every endpoint checks access through app/api/ownership.py (T28, T33): the video and the
job for the video routes, the job for the claim route. An object the caller may not see
is a 404, the same as a missing one.

T34: a reviewer who hasn't yet given their blind judgement on the job's open HIGH
review case gets 403 ``PRE_REVEAL_REQUIRED`` (``app.services.blind_review``), so these
routes can't be used to skip the blind step.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import ownership
from app.api.result_models import ClaimEvidenceResponse, ClaimsResponse, JobResultResponse
from app.auth.dependencies import get_current_user
from app.db.models.claim import ClaimRow
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.session import get_db
from app.services.blind_review import require_revealed
from app.services.reanalysis_service import is_finished, latest_finished_first
from app.services.result_view_service import claim_views, evidence_views, job_result, review_case

router = APIRouter(prefix="/v1", tags=["results"])

REVIEW_REJECTED = "REVIEW_REJECTED"


def _latest_job(db: Session, video_id: str, user: dict) -> Job:
    """The video's current result (T55): the newest finished job the caller may see, so
    a re-analysis that is still running or failed doesn't hide the last result. With no
    finished job, the newest job (answered with 202 / 409)."""
    ownership.video_or_404(db, video_id, user)
    job = latest_finished_first(
        db,
        ownership.visible_jobs(db.query(Job), user)
        .filter(Job.video_id == video_id)
        .order_by(Job.created_at.desc(), Job.id.desc()),
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return job


def _finished(job: Job) -> bool:
    """A result can be shown: done, in review, or rejected by a reviewer (the rejected
    result stays readable so the page can say why)."""
    return is_finished(job)


def _result_or_error(db: Session, job: Job) -> Result:
    if job.status in (JobStatus.PENDING, JobStatus.STARTED):
        raise HTTPException(status_code=202, detail=f"Job not complete — status: {job.status.value}")
    if not _finished(job):
        raise HTTPException(status_code=409, detail={"status": job.status.value, "error_code": job.error_code})
    result = db.query(Result).filter(Result.job_id == job.id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@router.get("/videos/{video_id}/results", response_model=JobResultResponse)
def get_video_results(video_id: str, db: Session = Depends(get_db),
                      current_user: dict = Depends(get_current_user)):
    job = _latest_job(db, video_id, current_user)
    require_revealed(db, job, current_user)
    return job_result(db, job, _result_or_error(db, job))


@router.get("/videos/{video_id}/claims", response_model=ClaimsResponse)
def get_video_claims(video_id: str, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    job = _latest_job(db, video_id, current_user)
    require_revealed(db, job, current_user)
    _result_or_error(db, job)
    return ClaimsResponse(job_id=job.id, video_id=video_id,
                          claims=claim_views(db, job.id, review_case(db, job.id)))


@router.get("/claims/{claim_id}/evidence", response_model=ClaimEvidenceResponse)
def get_claim_evidence(claim_id: str, db: Session = Depends(get_db),
                       current_user: dict = Depends(get_current_user)):
    claim = db.get(ClaimRow, claim_id)
    job = db.get(Job, claim.job_id) if claim is not None else None
    if claim is None or job is None or not ownership.can_view_job(job, current_user):
        raise HTTPException(status_code=404, detail="Claim not found")
    require_revealed(db, job, current_user)
    return ClaimEvidenceResponse(claim_id=claim.claim_id, id=claim.id, job_id=job.id,
                                 evidence=evidence_views(claim, cited_only=False))
