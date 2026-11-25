from typing import Optional
from pydantic import BaseModel


class RiskExplanationResponse(BaseModel):
    risk_finding_id: str
    risk: dict
    why_it_matters: str

    supporting_evidence: list[dict]
    rejected_evidence: list[dict]

    uncertainties: list[str]
    evidence_summary: dict

    recommended_action: str
    human_review_required: bool