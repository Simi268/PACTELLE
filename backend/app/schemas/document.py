from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


DocumentStatus = Literal[
    "uploaded",
    "processing",
    "completed",
    "failed"
]


class DocumentStatusUpdateRequest(BaseModel):
    processing_status: DocumentStatus


class DocumentResponse(BaseModel):
    id: UUID
    contract_id: UUID
    original_filename: str
    file_type: str
    file_size: int
    processing_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)