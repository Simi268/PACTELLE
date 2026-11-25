from pydantic import BaseModel
from typing import Optional


class RiskScoreFactors(BaseModel):
    severity: float
    deadline_urgency: float
    evidence_completeness: float
    verification: float
    evidence_confidence: float


class RiskScoreEvidence(BaseModel):
    total: int
    verified: int
    missing_or_incomplete: list[str]


class RiskScoreResponse(BaseModel):
    risk_finding_id: str
    contract_id: str
    title: str
    risk_type: str
    severity: str
    status: str

    risk_score: float
    priority: str

    evidence_confidence: Optional[float]

    factors: RiskScoreFactors
    evidence: RiskScoreEvidence

    explanation: str