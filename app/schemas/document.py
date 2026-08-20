from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


DocumentProcessingStatus = Literal["PENDING", "PROCESSING", "PROCESSED", "FAILED"]


class DocumentPublic(BaseModel):
    id: int
    original_filename: str
    content_type: str
    file_size: int
    status: DocumentProcessingStatus
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatus(BaseModel):
    document_id: int
    status: DocumentProcessingStatus
