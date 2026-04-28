import logging

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "who_infodemic_monitor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.autodiscover_tasks(["app.worker"])
celery_app.conf.update(task_track_started=True)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    if settings.WHISPER_PROVIDER == "faster_whisper":
        from app.core.extraction.transcription import get_whisper_model
        get_whisper_model()
        logger.info("faster-whisper model pre-loaded on worker startup")
