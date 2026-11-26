from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ActionPriority = Literal["critical", "high", "medium", "low"]
ActionStatus = Literal[
    "proposed", "approved", "rejected", "in_progress", "completed"
]


class PortfolioActionCreate(BaseModel):
    finding_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: ActionPriority
    due_date: date | None = None
    assigned_to_user_id: UUID | None = None


class PortfolioActionAssignmentUpdate(BaseModel):
    assigned_to_user_id: UUID | None = None


class PortfolioActionStatusUpdate(BaseModel):
    status: ActionStatus
    comment: str | None = Field(default=None, max_length=4000)


class PortfolioActionAuditResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    previous_status: str | None
    new_status: str | None
    comment: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioActionFindingReference(BaseModel):
    id: UUID
    title: str
    finding_type: str
    severity: str
    assessment_status: str
    status: str


class PortfolioActionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    finding_id: UUID
    title: str
    description: str
    rationale: str
    priority: ActionPriority
    status: ActionStatus
    assigned_to_user_id: UUID | None
    created_by_user_id: UUID | None
    due_date: date | None
    created_at: datetime
    updated_at: datetime
    finding: PortfolioActionFindingReference | None = None
    audit_entries: list[PortfolioActionAuditResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PortfolioActionListResponse(BaseModel):
    organization_id: UUID
    total: int
    page: int
    page_size: int
    total_pages: int
    actions: list[PortfolioActionResponse]


class PortfolioActionRecommendationResponse(BaseModel):
    organization_id: UUID
    finding_id: UUID
    created_count: int
    existing_count: int
    actions: list[PortfolioActionResponse]
