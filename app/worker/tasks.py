import logging
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.services.document_processing import DocumentProcessingError, process_document
from app.worker.celery_app import celery_app


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _public_failure_message(exc: Exception) -> str:
    if isinstance(exc, DocumentProcessingError):
        return str(exc)
    return "Document processing failed"


@celery_app.task(name="app.worker.tasks.process_document_task")
def process_document_task(document_id: int, job_id: int) -> None:
    """Process one document and persist its job lifecycle in a worker session."""
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            raise ValueError(f"Processing job {job_id} was not found")
        if job.document_id != document_id:
            raise ValueError(
                f"Processing job {job_id} does not belong to document {document_id}"
            )

        job.status = "STARTED"
        job.started_at = _utc_now()
        job.error_message = None
        db.commit()
        logger.info(
            "Processing job started document_id=%s job_id=%s",
            document_id,
            job_id,
        )

        process_document(document_id, db)

        job = db.get(ProcessingJob, job_id)
        if job is None:
            raise ValueError(f"Processing job {job_id} was deleted during processing")
        job.status = "SUCCESS"
        job.finished_at = _utc_now()
        db.commit()
        logger.info(
            "Processing job completed document_id=%s job_id=%s",
            document_id,
            job_id,
        )
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Celery task failed for document %s and job %s", document_id, job_id
        )

        try:
            failed_job = db.get(ProcessingJob, job_id)
            if failed_job is not None:
                failed_job.status = "FAILED"
                failed_job.error_message = _public_failure_message(exc)
                failed_job.finished_at = _utc_now()

            document = db.get(Document, document_id)
            if document is not None:
                document.status = "FAILED"

            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Could not persist failure for document %s and job %s",
                document_id,
                job_id,
            )
        raise
    finally:
        db.close()
