import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path as PathParameter,
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
from app.schemas.error import ClientErrorResponse, ErrorResponse
from app.schemas.job import ProcessingJobQueued
from app.services.document_processing import DocumentProcessingError
from app.services.storage import EmptyFileError, FileTooLargeError, LocalFileStorage
from app.worker.tasks import process_document_task


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

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

    content_type = (upload.content_type or "").lower().split(";", maxsplit=1)[0].strip()
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
    summary="Upload a document",
    description=(
        "Upload a non-empty text or PDF document. The configured upload-size limit "
        f"is {settings.MAX_UPLOAD_SIZE_MB} MB."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "The upload filename is missing or too long.",
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "The file exceeds the configured upload-size limit.",
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "model": ErrorResponse,
            "description": "The filename or content type is unsupported.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ClientErrorResponse,
            "description": "The upload is empty or request validation failed.",
        },
    },
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
    except EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file must not be empty",
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit",
        ) from exc
    except OSError as exc:
        logger.exception("Could not store uploaded document user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store uploaded document",
        ) from exc

    normalized_content_type = (
        (file.content_type or "").lower().split(";", maxsplit=1)[0].strip()
    )

    document = Document(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=stored_file.stored_filename,
        content_type=normalized_content_type,
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
        logger.exception("Could not persist uploaded document user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save document metadata",
        ) from exc
    db.refresh(document)
    logger.info(
        "Document uploaded document_id=%s user_id=%s size_bytes=%s type=%s",
        document.id,
        current_user.id,
        document.file_size,
        document.content_type,
    )
    return document


@router.get(
    "",
    response_model=list[DocumentPublic],
    summary="List documents",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
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


@router.get(
    "/{document_id}",
    response_model=DocumentPublic,
    summary="Get a document",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def get_document(
    document_id: Annotated[int, PathParameter(gt=0, description="Document ID")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return _owned_document(db, document_id, current_user.id)


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatus,
    summary="Get document processing status",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def get_document_status(
    document_id: Annotated[int, PathParameter(gt=0, description="Document ID")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentStatus:
    document = _owned_document(db, document_id, current_user.id)
    return DocumentStatus(document_id=document.id, status=document.status)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Delete a document unless it has a queued or running processing job.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The document is actively processing.",
        },
    },
)
def delete_document(
    document_id: Annotated[int, PathParameter(gt=0, description="Document ID")],
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
        logger.exception("Could not delete document_id=%s", document.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete document",
        ) from exc

    try:
        LocalFileStorage.remove(storage_path)
    except OSError:
        logger.exception(
            "Document metadata deleted but stored file cleanup failed document_id=%s",
            document_id,
        )

    logger.info("Document deleted document_id=%s user_id=%s", document_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/process",
    response_model=ProcessingJobQueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue document processing",
    description=(
        "Queue text extraction and indexing. A document may have only one active "
        "processing job."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The document is already processing or is in an invalid state.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "The processing task could not be queued.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ClientErrorResponse,
            "description": "Document extraction or request validation failed.",
        },
    },
)
def process_owned_document(
    document_id: Annotated[int, PathParameter(gt=0, description="Document ID")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobQueued:
    document = _owned_document(db, document_id, current_user.id)

    active_job = db.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status.in_(("QUEUED", "STARTED")),
        )
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
    )
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already has an active processing job",
        )

    if document.status not in {"PENDING", "PROCESSED", "FAILED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document cannot be processed while in {document.status} status",
        )

    job = ProcessingJob(document_id=document_id, status="QUEUED")
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not create processing job document_id=%s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create processing job",
        ) from exc

    try:
        task = process_document_task.delay(document_id, job.id)
    except DocumentProcessingError as exc:
        db.expire_all()
        logger.warning(
            "Document processing failed before queue response document_id=%s job_id=%s",
            document_id,
            job.id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Could not enqueue processing document_id=%s job_id=%s",
            document_id,
            job.id,
        )
        job.status = "FAILED"
        job.error_message = "Could not enqueue document processing"
        job.finished_at = datetime.now(timezone.utc)
        document.status = "FAILED"
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Could not persist enqueue failure document_id=%s job_id=%s",
                document_id,
                job.id,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not enqueue document processing",
        ) from exc

    job.celery_task_id = task.id
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Processing task id persistence failed document_id=%s job_id=%s",
            document_id,
            job.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Processing task was enqueued but its task id could not be saved",
        ) from exc
    logger.info(
        "Processing job queued document_id=%s job_id=%s task_id=%s",
        document_id,
        job.id,
        task.id,
    )
    return ProcessingJobQueued(
        document_id=document_id,
        job_id=job.id,
        status="QUEUED",
    )
