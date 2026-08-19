from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProcessingJobQueued(BaseModel):
    document_id: int
    job_id: int
    status: str


class ProcessingJobPublic(BaseModel):
    id: int
    document_id: int
    status: str
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
