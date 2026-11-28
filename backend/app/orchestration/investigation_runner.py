"""Investigation Agent for PACTELLE.

Reconstructs the history of an existing risk finding using
persisted risk events and the existing deterministic investigation
service.

This agent is read-only. It does not create or modify risk records.
"""

from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    EvidenceReference,
)
from app.agents.state import AgentState

from app.core.database import SessionLocal

from app.models.contract import Contract
from app.models.evidence_record import EvidenceRecord
from app.models.risk_event import RiskEvent
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence

from app.services.risk_investigation import reconstruct_investigation


class InvestigationAgent:
    agent_name = AgentName.INVESTIGATION

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        investigation_service: Callable = reconstruct_investigation,
    ):
        self.session_factory = session_factory
        self.investigation_service = investigation_service

    def __call__(self, state: AgentState) -> AgentResult:
        db = None

        try:
            finding_id = state.task.input_data.get("risk_finding_id")

            if not finding_id:
                return self._failure(
                    "MISSING_RISK_FINDING_ID",
                    "A risk finding ID is required for investigation.",
                )

            try:
                finding_uuid = UUID(str(finding_id))
            except (ValueError, TypeError, AttributeError):
                return self._failure(
                    "INVALID_RISK_FINDING_ID",
                    "The supplied risk finding ID is not a valid UUID.",
                )

            session_factory = self.session_factory or SessionLocal
            db = session_factory()

            finding = (
                db.query(RiskFinding)
                .join(
                    Contract,
                    Contract.id == RiskFinding.contract_id,
                )
                .options(
                    joinedload(
                        RiskFinding.evidence_links
                    ).joinedload(
                        RiskFindingEvidence.evidence_record
                    ).joinedload(
                        EvidenceRecord.clause
                    ),
                    joinedload(
                        RiskFinding.evidence_links
                    ).joinedload(
                        RiskFindingEvidence.evidence_record
                    ).joinedload(
                        EvidenceRecord.document
                    ),
                )
                .filter(
                    RiskFinding.id == finding_uuid,
                    Contract.organization_id == state.organization_id,
                )
                .first()
            )

            if finding is None:
                return self._failure(
                    "RISK_FINDING_NOT_FOUND",
                    "No risk finding was found for this organization.",
                )

            events = (
                db.query(RiskEvent)
                .filter(
                    RiskEvent.risk_finding_id == finding_uuid,
                    RiskEvent.contract_id == finding.contract_id,
                )
                .order_by(
                    RiskEvent.created_at.asc(),
                    RiskEvent.id.asc(),
                )
                .all()
            )

            investigation = self.investigation_service(
                finding,
                events,
            )

            if not isinstance(investigation, dict):
                return self._failure(
                    "INVALID_INVESTIGATION_RESULT",
                    "The investigation service returned an invalid result.",
                )

            required_fields = {
                "risk_finding_id",
                "risk_overview",
                "investigation_summary",
                "timeline",
                "evidence_evolution",
                "assessment_evolution",
                "current_evidence",
                "unresolved_questions",
                "recommended_action",
                "human_review_required",
            }

            missing_fields = required_fields - investigation.keys()

            if missing_fields:
                return self._failure(
                    "INCOMPLETE_INVESTIGATION_RESULT",
                    "The investigation result is missing required fields.",
                    data={"missing_fields": sorted(missing_fields)},
                )

            if investigation["risk_finding_id"] != str(finding_uuid):
                return self._failure(
                    "INVESTIGATION_ID_MISMATCH",
                    "The investigation result does not match the requested finding.",
                )

            unresolved_questions = investigation["unresolved_questions"]

            if not isinstance(unresolved_questions, list):
                return self._failure(
                    "INVALID_UNRESOLVED_QUESTIONS",
                    "Investigation unresolved questions must be a list.",
                )

            evidence_references = self._collect_evidence_references(
                finding
            )

            human_review_required = (
                bool(investigation["human_review_required"])
                or bool(unresolved_questions)
            )

            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary=(
                    "Risk investigation reconstructed from persisted history."
                ),
                data=investigation,
                evidence_references=evidence_references,
                unresolved_questions=unresolved_questions,
                human_review_required=human_review_required,
            )

        except Exception as exc:
            return self._failure(
                "INVESTIGATION_EXECUTION_FAILED",
                str(exc),
            )

        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _collect_evidence_references(finding):
        references = []

        for link in finding.evidence_links or []:
            evidence = link.evidence_record

            if evidence is None:
                continue

            document = evidence.document

            references.append(
                EvidenceReference(
                    evidence_id=str(evidence.id),
                    document_id=(
                        str(document.id) if document else None
                    ),
                    contract_id=str(finding.contract_id),
                    clause_id=(
                        str(evidence.clause_id)
                        if evidence.clause_id else None
                    ),
                    page_number=evidence.page_number,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                    excerpt=evidence.evidence_text,
                    verification_status=evidence.verification_status,
                )
            )

        return references

    def _failure(
        self,
        code: str,
        message: str,
        data: Optional[dict] = None,
    ) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Risk investigation could not be completed.",
            data=data or {},
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )