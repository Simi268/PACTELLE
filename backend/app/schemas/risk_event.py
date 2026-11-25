from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RiskEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    risk_finding_id: UUID | None
    contract_id: UUID
    event_type: str
    source: str
    actor_id: UUID | None
    summary: str
    previous_state: dict[str, Any] | None
    new_state: dict[str, Any] | None
    evidence_snapshot: Any | None
    created_at: datetime


class RiskEventTimelineResponse(BaseModel):
    organization_id: UUID
    total: int
    page: int
    page_size: int
    total_pages: int
    events: list[RiskEventResponse]