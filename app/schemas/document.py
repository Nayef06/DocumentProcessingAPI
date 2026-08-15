from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentPublic(BaseModel):
    id: int
    original_filename: str
    content_type: str
    file_size: int
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatus(BaseModel):
    document_id: int
    status: str
