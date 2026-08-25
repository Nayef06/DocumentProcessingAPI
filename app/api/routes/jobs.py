from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.job import ProcessingJobPublic
from app.schemas.error import ErrorResponse


router = APIRouter(prefix="/jobs", tags=["Processing Jobs"])


@router.get(
    "/{job_id}",
    response_model=ProcessingJobPublic,
    summary="Get a processing job",
    description="Check the status of a processing job for one of your documents.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def get_processing_job(
    job_id: Annotated[int, Path(gt=0, description="Processing job ID")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJob:
    job = db.scalar(
        select(ProcessingJob)
        .join(Document, ProcessingJob.document_id == Document.id)
        .where(
            ProcessingJob.id == job_id,
            Document.user_id == current_user.id,
        )
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found",
        )
    return job
