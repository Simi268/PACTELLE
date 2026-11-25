from datetime import datetime
from pydantic import BaseModel


class RiskInvestigationResponse(BaseModel):

    risk_finding_id: str

    risk_overview: dict

    investigation_summary: dict

    timeline: list[dict]

    evidence_evolution: list[dict]

    assessment_evolution: list[dict]

    current_evidence: dict

    unresolved_questions: list[str]

    recommended_action: str

    human_review_required: bool