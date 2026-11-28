"""PACTELLE Recommendation Agent.

Generates deterministic, evidence-linked action proposals.
Read-only: does not execute recommendations or mutate database records.
"""

import logging
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.orm import Session, selectinload, joinedload

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    EvidenceReference,
)
from app.agents.state import AgentState
from app.core.database import SessionLocal
from app.models.evidence_record import EvidenceRecord
from app.models.portfolio_risk_finding import (
    PortfolioRiskFinding,
    PortfolioRiskFindingEvidence,
)
from app.services.portfolio_action_recommender import recommend_actions

logger = logging.getLogger(__name__)


class RecommendationAgent:
    agent_name = AgentName.RECOMMENDATION

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        recommendation_service: Callable = recommend_actions,
    ):
        self.session_factory = session_factory
        self.recommendation_service = recommendation_service

    def __call__(self, state: AgentState) -> AgentResult:
        db = None

        try:
            finding_id = state.task.input_data.get(
                "portfolio_finding_id"
            )

            if not finding_id:
                return self._failure(
                    "MISSING_PORTFOLIO_FINDING_ID",
                    "A portfolio finding ID is required.",
                )

            try:
                finding_uuid = UUID(str(finding_id))
            except (ValueError, TypeError, AttributeError):
                return self._failure(
                    "INVALID_PORTFOLIO_FINDING_ID",
                    "The portfolio finding ID is not a valid UUID.",
                )

            session_factory = self.session_factory or SessionLocal
            db = session_factory()

            finding = (
                db.query(PortfolioRiskFinding)
                .filter(
                    PortfolioRiskFinding.id == finding_uuid,
                    PortfolioRiskFinding.organization_id
                    == state.organization_id,
                )
                .options(
                    selectinload(
                        PortfolioRiskFinding.evidence_links
                    ).joinedload(
                        PortfolioRiskFindingEvidence.evidence_record
                    ).joinedload(
                        EvidenceRecord.document
                    ),
                    selectinload(
                        PortfolioRiskFinding.evidence_links
                    ).joinedload(
                        PortfolioRiskFindingEvidence.evidence_record
                    ).joinedload(
                        EvidenceRecord.clause
                    ),
                )
                .first()
            )

            if finding is None:
                return self._failure(
                    "PORTFOLIO_FINDING_NOT_FOUND",
                    "The requested finding was not found in this organization.",
                )

            recommendations = self.recommendation_service(finding)

            if not isinstance(recommendations, list):
                return self._failure(
                    "INVALID_RECOMMENDATION_OUTPUT",
                    "The recommendation service returned an invalid result.",
                )

            for recommendation in recommendations:
                if not isinstance(recommendation, dict):
                    return self._failure(
                        "INVALID_RECOMMENDATION_OUTPUT",
                        "A recommendation has an invalid structure.",
                    )

                required_fields = {
                    "title",
                    "description",
                    "rationale",
                    "priority",
                    "due_days",
                    "requires_human_review",
                    "legal_conclusion",
                }

                if not required_fields.issubset(recommendation):
                    return self._failure(
                        "INCOMPLETE_RECOMMENDATION",
                        "A recommendation is missing required fields.",
                    )

                # Enforce safety invariants at the agent boundary.
                if recommendation["requires_human_review"] is not True:
                    return self._failure(
                        "HUMAN_REVIEW_INVARIANT_VIOLATION",
                        "Recommendations must require human review.",
                    )

                if recommendation["legal_conclusion"] is not False:
                    return self._failure(
                        "LEGAL_CONCLUSION_INVARIANT_VIOLATION",
                        "Recommendations cannot establish legal conclusions.",
                    )

            evidence_references = []
            unresolved = []

            for link in finding.evidence_links or []:
                evidence = link.evidence_record

                if evidence is None:
                    unresolved.append(
                        "A finding evidence link references a missing record."
                    )
                    continue

                document = evidence.document
                clause = evidence.clause

                evidence_references.append(
                    EvidenceReference(
                        evidence_id=str(evidence.id),
                        document_id=str(evidence.document_id),
                        contract_id=(
                            str(document.contract_id)
                            if document else None
                        ),
                        clause_id=str(evidence.clause_id),
                        page_number=evidence.page_number,
                        char_start=evidence.char_start,
                        char_end=evidence.char_end,
                        excerpt=evidence.evidence_text,
                        verification_status=evidence.verification_status,
                    )
                )

                if evidence.verification_status != "verified":
                    unresolved.append(
                        f"Evidence {evidence.id} is "
                        f"{evidence.verification_status}."
                    )

                if document is None or clause is None:
                    unresolved.append(
                        f"Evidence {evidence.id} has incomplete provenance."
                    )

            if not recommendations:
                unresolved.append(
                    "No recommendation template exists for this finding type."
                )

            if finding.assessment_status != "confirmed":
                unresolved.append(
                    "The finding is provisional and requires assessment."
                )

            unresolved = list(dict.fromkeys(unresolved))

            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary=(
                    f"Generated {len(recommendations)} recommendation(s) "
                    f"for finding {finding.id}. "
                    "Human approval is required before action."
                ),
                data={
                    "portfolio_finding_id": str(finding.id),
                    "finding_type": finding.finding_type,
                    "finding_title": finding.title,
                    "finding_severity": finding.severity,
                    "finding_assessment_status": finding.assessment_status,
                    "recommendations": recommendations,
                    "recommendation_count": len(recommendations),
                    "execution_performed": False,
                    "database_mutation_performed": False,
                    "legal_conclusions_established": False,
                },
                evidence_references=evidence_references,
                unresolved_questions=unresolved,
                human_review_required=True,
            )

        except Exception:
            logger.exception(
                "Recommendation Agent failed for organization %s",
                state.organization_id,
            )

            return self._failure(
                "RECOMMENDATION_GENERATION_FAILED",
                "Recommendation generation failed. No action was executed.",
            )

        finally:
            if db is not None:
                db.close()

    def _failure(self, code: str, message: str) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Recommendation generation did not complete.",
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )