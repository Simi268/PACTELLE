from datetime import datetime
from typing import Any, Literal
from uuid import UUID


from pydantic import BaseModel, ConfigDict, Field


PortfolioFindingStatus = Literal[
    "open",
    "acknowledged",
    "resolved",
]

PortfolioFindingType = Literal[
    "similarity",
    "potential_conflict",
    "repeated_risk",
    "exposure_concentration",
]

PortfolioFindingSeverity = Literal[
    "critical",
    "high",
    "medium",
    "low",
]


class PortfolioFindingStatusUpdate(BaseModel):
    status: PortfolioFindingStatus


class PortfolioContractReference(BaseModel):
    id: UUID
    title: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class PortfolioEvidenceReference(BaseModel):
    evidence_id: UUID
    contract_id: UUID
    contract_title: str | None = None

    evidence_type: str
    claim: str
    evidence_text: str

    verification_status: str
    confidence: float | None = None

    page_number: int | None = None
    clause_id: UUID | None = None
    document_id: UUID


class PortfolioFindingResponse(BaseModel):
    id: UUID
    organization_id: UUID

    finding_type: str
    title: str
    description: str

    severity: str
    status: str
    assessment_status: str

    detection_method: str
    rule_id: str
    rule_version: str

    confidence: float | None = None
    details: Any | None = None

    created_at: datetime

    contracts: list[PortfolioContractReference]
    evidence: list[PortfolioEvidenceReference]


class PortfolioFindingListResponse(BaseModel):
    organization_id: UUID

    total: int
    page: int
    page_size: int
    total_pages: int

    findings: list[PortfolioFindingResponse]

class PortfolioAnalysisSummary(BaseModel):
    retrieval: dict[str, Any]
    intelligence: dict[str, Any]
    generation: dict[str, Any]
    persistence: dict[str, int]


class PortfolioAnalysisResponse(BaseModel):
    organization_id: UUID
    status: Literal["completed"]

    summary: PortfolioAnalysisSummary

    findings: list[PortfolioFindingResponse]
    human_review_queue: list[dict[str, Any]]

class PortfolioEvolutionResponse(BaseModel):
    organization_id: UUID

    previous_snapshot_id: UUID
    current_snapshot_id: UUID

    previous_snapshot_created_at: datetime
    current_snapshot_created_at: datetime

    summary: dict[str, int]
    findings: list[dict[str, Any]]

    human_review_required: bool