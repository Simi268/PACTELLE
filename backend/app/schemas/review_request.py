from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReviewType = Literal["evidence_verification", "interpretation", "legal_review", "action_approval"]
ReviewStatus = Literal["pending", "approved", "rejected", "clarification_requested", "cancelled"]


class ReviewRequestCreate(BaseModel):
    review_type: ReviewType
    reason: str = Field(min_length=8, max_length=5000)
    evidence_record_ids: list[UUID] = Field(min_length=1, max_length=50)
    execution_id: UUID | None = None
    subject_type: str | None = Field(default=None, max_length=50)
    subject_id: UUID | None = None
    proposed_interpretation: str | None = Field(default=None, max_length=10000)
    assigned_to_user_id: UUID | None = None

    @model_validator(mode="after")
    def unique_evidence(self):
        if len(self.evidence_record_ids) != len(set(self.evidence_record_ids)):
            raise ValueError("evidence_record_ids must not contain duplicates")
        return self


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected", "clarification_requested"]
    comment: str = Field(min_length=3, max_length=5000)


class ReviewAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    previous_status: str | None
    new_status: str | None
    comment: str | None
    created_at: datetime


class ReviewRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    execution_id: UUID | None
    review_type: str
    subject_type: str | None
    subject_id: UUID | None
    status: str
    reason: str
    proposed_interpretation: str | None
    evidence_snapshot: list[dict]
    requested_by_user_id: UUID | None
    assigned_to_user_id: UUID | None
    decided_by_user_id: UUID | None
    decision_comment: str | None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    audit_entries: list[ReviewAuditResponse] = Field(default_factory=list)


class ReviewRequestListResponse(BaseModel):
    organization_id: UUID
    total: int
    reviews: list[ReviewRequestResponse]
