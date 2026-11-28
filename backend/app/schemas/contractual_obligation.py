from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ObligationStatus = Literal["open", "in_progress", "completed", "waived"]


class ObligationSyncResponse(BaseModel):
    organization_id: UUID
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_rejected_count: int
    unsupported_count: int
    total_current_records: int


class ObligationUpdate(BaseModel):
    due_date: date | None = None
    assigned_to_user_id: UUID | None = None
    status: ObligationStatus | None = None
    completion_note: str | None = Field(default=None, max_length=5000)
    completion_evidence_record_id: UUID | None = None
    waived_reason: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=4000)


class ObligationAuditResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    previous_status: str | None
    new_status: str | None
    comment: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractualObligationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    contract_id: UUID
    evidence_record_id: UUID
    obligation_type: str
    obligation_family: str
    description: str
    claim: str
    original_text: str
    duration: dict | None
    verification_status: str
    confidence: float | None
    due_date: date | None
    status: ObligationStatus
    assigned_to_user_id: UUID | None
    completion_note: str | None
    completion_evidence_record_id: UUID | None
    completed_at: datetime | None
    waived_reason: str | None
    created_at: datetime
    updated_at: datetime
    overdue: bool
    audit_entries: list[ObligationAuditResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ContractualObligationListResponse(BaseModel):
    organization_id: UUID
    total: int
    page: int
    page_size: int
    total_pages: int
    obligations: list[ContractualObligationResponse]
