from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ProcessingJobStatus = Literal["QUEUED", "STARTED", "SUCCESS", "FAILED"]
ActiveProcessingJobStatus = Literal["QUEUED", "STARTED"]


class ProcessingJobQueued(BaseModel):
    document_id: int
    job_id: int
    status: ActiveProcessingJobStatus


class ProcessingJobPublic(BaseModel):
    id: int
    document_id: int
    status: ProcessingJobStatus
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
