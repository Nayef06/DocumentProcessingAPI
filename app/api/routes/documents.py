from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.document import DocumentPublic, DocumentStatus
from app.schemas.job import ProcessingJobQueued
from app.services.storage import FileTooLargeError, LocalFileStorage
from app.worker.tasks import process_document_task


router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    ".txt": {"text/plain", "application/octet-stream"},
    ".pdf": {"application/pdf", "application/octet-stream"},
}


def _validate_upload(upload: UploadFile) -> tuple[str, str]:
    original_filename = Path(upload.filename or "").name
    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename",
        )
    if len(original_filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must be 255 characters or fewer",
        )

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .txt and .pdf files are supported",
        )

    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content type does not match the {extension} file extension",
        )
    return original_filename, extension


def _owned_document(db: Session, document_id: int, user_id: int) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@router.post(
    "/upload",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: Annotated[UploadFile, File(description="A .txt or .pdf document")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    original_filename, extension = _validate_upload(file)
    storage = LocalFileStorage(
        upload_dir=settings.UPLOAD_DIR,
        max_size_bytes=settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024,
    )
    try:
        stored_file = storage.save(file, extension)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit",
        ) from exc

    document = Document(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=stored_file.stored_filename,
        content_type=file.content_type.lower(),
        file_size=stored_file.file_size,
        storage_path=stored_file.storage_path,
        status="PENDING",
        metadata_json={"extension": extension},
    )
    db.add(document)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        storage.remove(stored_file.storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save document metadata",
        ) from exc
    db.refresh(document)
    return document


@router.get("", response_model=list[DocumentPublic])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == current_user.id)
            .order_by(Document.created_at.desc(), Document.id.desc())
        ).all()
    )


@router.get("/{document_id}", response_model=DocumentPublic)
def get_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return _owned_document(db, document_id, current_user.id)


@router.get("/{document_id}/status", response_model=DocumentStatus)
def get_document_status(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentStatus:
    document = _owned_document(db, document_id, current_user.id)
    return DocumentStatus(document_id=document.id, status=document.status)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    document = _owned_document(db, document_id, current_user.id)
    active_job = db.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(("QUEUED", "STARTED")),
        )
    )
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document cannot be deleted while processing is active",
        )

    storage_path = document.storage_path
    db.delete(document)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete document",
        ) from exc

    try:
        LocalFileStorage.remove(storage_path)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document was deleted, but its stored file could not be removed",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/process",
    response_model=ProcessingJobQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_owned_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobQueued:
    _owned_document(db, document_id, current_user.id)

    active_job = db.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status.in_(("QUEUED", "STARTED")),
        )
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
    )
    if active_job is not None:
        return ProcessingJobQueued(
            document_id=document_id,
            job_id=active_job.id,
            status=active_job.status,
        )

    job = ProcessingJob(document_id=document_id, status="QUEUED")
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create processing job",
        ) from exc

    try:
        task = process_document_task.delay(document_id, job.id)
    except Exception as exc:
        job.status = "FAILED"
        job.error_message = f"Could not enqueue processing task: {exc}"
        job.finished_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not enqueue document processing",
        ) from exc

    job.celery_task_id = task.id
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Processing task was enqueued but its task id could not be saved",
        ) from exc
    return ProcessingJobQueued(
        document_id=document_id,
        job_id=job.id,
        status="QUEUED",
    )
