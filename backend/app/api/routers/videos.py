from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.services.video_service import save_video

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("/upload")
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    content = file.file.read()
    video = save_video(db, content, file.filename or "upload.mp4")
    return {
        "video_id": video.id,
        "filename": video.filename,
        "file_size": video.file_size,
    }
