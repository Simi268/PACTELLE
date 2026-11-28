from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =========================================================
# ENUMS / TYPES
# =========================================================

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


# =========================================================
# PORTFOLIO FINDING REQUEST SCHEMAS
# =========================================================

class PortfolioFindingStatusUpdate(BaseModel):
    status: PortfolioFindingStatus


# =========================================================
# PORTFOLIO FINDING REFERENCE SCHEMAS
# =========================================================

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

    char_start: int | None = None
    char_end: int | None = None


# =========================================================
# PORTFOLIO FINDING RESPONSE
# =========================================================

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


# =========================================================
# PORTFOLIO FINDING LIST RESPONSE
# =========================================================

class PortfolioFindingListResponse(BaseModel):
    organization_id: UUID

    total: int
    page: int
    page_size: int
    total_pages: int

    findings: list[PortfolioFindingResponse]


# =========================================================
# PORTFOLIO ANALYSIS RESPONSE
# =========================================================

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


# =========================================================
# PORTFOLIO EVOLUTION RESPONSE
# =========================================================

class PortfolioEvolutionResponse(BaseModel):
    organization_id: UUID

    previous_snapshot_id: UUID
    current_snapshot_id: UUID

    previous_snapshot_created_at: datetime
    current_snapshot_created_at: datetime

    summary: dict[str, int]
    findings: list[dict[str, Any]]

    human_review_required: bool


# =========================================================
# PORTFOLIO SNAPSHOT HISTORY
# =========================================================

class PortfolioSnapshotListItem(BaseModel):
    id: UUID
    organization_id: UUID

    analysis_version: str

    total_contracts: int
    total_obligations: int
    total_comparisons: int
    total_findings: int

    summary: dict[str, Any]
    created_at: datetime


class PortfolioSnapshotListResponse(BaseModel):
    organization_id: UUID

    total: int
    page: int
    page_size: int
    total_pages: int

    snapshots: list[PortfolioSnapshotListItem]


# =========================================================
# PORTFOLIO SNAPSHOT FINDING RESPONSE
# =========================================================

class PortfolioSnapshotFindingResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    portfolio_finding_id: UUID | None = None

    rule_id: str
    finding_type: str
    title: str
    description: str

    severity: str
    status: str
    assessment_status: str

    details: Any | None = None

    contract_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    captured_at: datetime


# =========================================================
# PORTFOLIO SNAPSHOT DETAIL RESPONSE
# =========================================================

class PortfolioSnapshotDetailResponse(BaseModel):
    id: UUID
    organization_id: UUID

    analysis_version: str

    total_contracts: int
    total_obligations: int
    total_comparisons: int
    total_findings: int

    summary: dict[str, Any]
    created_at: datetime

    findings: list[PortfolioSnapshotFindingResponse]


# =========================================================
# PORTFOLIO RISK TREND RESPONSE
# =========================================================

class PortfolioRiskScoreTrend(BaseModel):
    initial: int
    latest: int
    change: int
    direction: Literal[
        "increasing",
        "decreasing",
        "stable",
    ]
    interpretation: str


class PortfolioFindingCountTrend(BaseModel):
    initial: int
    latest: int
    change: int


class PortfolioSnapshotTrendMetric(BaseModel):
    snapshot_id: UUID
    created_at: datetime

    total_findings: int

    severity_distribution: dict[str, int]
    weighted_risk_score: int


class PortfolioRiskPattern(BaseModel):
    rule_id: str
    title: str
    finding_type: str

    classification: Literal[
        "emerging",
        "persistent",
        "recurring",
        "not_detected_in_latest",
        "intermittent",
    ]

    appearances: int
    total_snapshots: int

    first_detected_at: datetime
    last_detected_at: datetime

    detected_in_latest_snapshot: bool

    latest_severity: str

    severity_history: list[str]
    status_history: list[str]
    assessment_status_history: list[str]

    contract_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    human_review_required: bool


class PortfolioRiskTrendResponse(BaseModel):
    organization_id: UUID

    snapshot_count: int

    first_snapshot_id: UUID
    latest_snapshot_id: UUID

    overall_trend: Literal[
        "increasing",
        "decreasing",
        "stable",
    ]

    risk_score: PortfolioRiskScoreTrend
    finding_count: PortfolioFindingCountTrend

    severity_distribution: dict[str, dict[str, int]]

    classification_summary: dict[str, int]

    snapshot_history: list[PortfolioSnapshotTrendMetric]

    risk_patterns: list[PortfolioRiskPattern]

    human_review_required: bool