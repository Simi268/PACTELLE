from uuid import UUID
from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ContractStatus = Literal[
    "draft",
    "active",
    "expired",
    "terminated"
]


class ContractCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    contract_type: str | None = Field(default=None, max_length=100)
    status: ContractStatus = "draft"
    effective_date: date | None = None
    expiration_date: date | None = None


class ContractUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    contract_type: str | None = Field(default=None, max_length=100)
    status: ContractStatus | None = None
    effective_date: date | None = None
    expiration_date: date | None = None


class ContractResponse(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    contract_type: str | None
    status: str
    effective_date: date | None
    expiration_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)