"""Obligation Agent for PACTELLE.

Coordinates existing obligation retrieval, normalization and context analysis.
Does not create or modify evidence or contractual lifecycle records.
"""

import logging
from typing import Callable, Optional
from uuid import UUID

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    EvidenceReference,
)
from app.agents.state import AgentState
from app.core.database import SessionLocal
from app.services.portfolio_obligation_service import (
    retrieve_organization_obligations,
)
from app.services.obligation_context_analyzer import (
    analyze_obligation_context,
)

logger = logging.getLogger(__name__)


class ObligationAgent:
    """Coordinates evidence-backed obligation analysis."""

    agent_name = AgentName.OBLIGATION

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        retriever: Callable = retrieve_organization_obligations,
        context_analyzer: Callable = analyze_obligation_context,
    ):
        # Resolve SessionLocal at runtime so tests can inject a session factory.
        self.session_factory = session_factory
        self.retriever = retriever
        self.context_analyzer = context_analyzer

    def __call__(self, state: AgentState) -> AgentResult:
        db = None

        try:
            organization_id = state.task.organization_id

            session_factory = self.session_factory or SessionLocal
            db = session_factory()

            retrieval = self.retriever(
                db,
                organization_id,
            )

            if not isinstance(retrieval, dict):
                return self._failure(
                    "INVALID_RETRIEVAL_RESPONSE",
                    "Obligation retrieval returned an invalid response.",
                )

            obligations = retrieval.get("obligations", [])
            excluded = retrieval.get("excluded_obligations", [])

            if not isinstance(obligations, list) or not isinstance(excluded, list):
                return self._failure(
                    "INVALID_OBLIGATION_COLLECTION",
                    "Retrieved obligation collections are invalid.",
                )

            analyzed_obligations = []
            unresolved_questions = []
            evidence_references = []

            for obligation in obligations:
                if not isinstance(obligation, dict):
                    unresolved_questions.append(
                        "A retrieved obligation has an invalid structure."
                    )
                    continue

                self._collect_evidence_reference(
                    obligation,
                    evidence_references,
                    unresolved_questions,
                )

                context = self.context_analyzer(obligation)

                analyzed_obligations.append({
                    **obligation,
                    "context_analysis": context,
                })

                self._collect_uncertainties(
                    obligation,
                    context,
                    unresolved_questions,
                )

            # Rejected evidence remains visible but is never sent through
            # eligible obligation context analysis.
            for obligation in excluded:
                if isinstance(obligation, dict):
                    self._collect_evidence_reference(
                        obligation,
                        evidence_references,
                        unresolved_questions,
                    )

            summary = retrieval.get("summary", {})

            if not isinstance(summary, dict):
                summary = {}

            if not analyzed_obligations:
                unresolved_questions.append(
                    "No eligible normalized obligations were available for analysis."
                )

            unsupported_count = summary.get("unsupported_evidence", 0)

            if unsupported_count:
                unresolved_questions.append(
                    f"{unsupported_count} evidence records could not be normalized "
                    "because their evidence types are unsupported."
                )

            # Preserve unique questions without changing their order.
            unresolved_questions = list(dict.fromkeys(unresolved_questions))

            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary=(
                    f"Analyzed {len(analyzed_obligations)} eligible obligations "
                    f"across {summary.get('contracts_with_obligations', 0)} contracts."
                ),
                data={
                    "organization_id": str(organization_id),
                    "summary": {
                        **summary,
                        "analyzed_obligations": len(analyzed_obligations),
                        "excluded_rejected_evidence": len(excluded),
                        "unresolved_question_count": len(unresolved_questions),
                    },
                    "obligations": analyzed_obligations,
                    "excluded_obligations": excluded,
                    "grouped_by_family": retrieval.get("grouped_by_family", {}),
                    "grouped_by_type": retrieval.get("grouped_by_type", {}),
                },
                evidence_references=evidence_references,
                unresolved_questions=unresolved_questions,
                human_review_required=bool(unresolved_questions),
            )

        except Exception:
            logger.exception(
                "Obligation Agent failed for organization %s",
                state.task.organization_id,
            )

            return self._failure(
                "OBLIGATION_ANALYSIS_FAILED",
                "Obligation retrieval or contextual analysis failed. "
                "No successful analysis is assumed.",
            )

        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _collect_evidence_reference(
        obligation: dict,
        references: list,
        unresolved_questions: list,
    ) -> None:
        evidence_id = obligation.get("evidence_id")
        provenance = obligation.get("provenance") or {}

        if not evidence_id:
            unresolved_questions.append(
                "An obligation is missing its evidence identifier."
            )
            return

        reference = EvidenceReference(
            evidence_id=str(evidence_id),
            document_id=provenance.get("document_id"),
            contract_id=obligation.get("contract_id"),
            clause_id=provenance.get("clause_id"),
            page_number=provenance.get("page_number"),
            char_start=provenance.get("char_start"),
            char_end=provenance.get("char_end"),
            excerpt=obligation.get("original_text"),
            verification_status=obligation.get("verification_status"),
        )

        references.append(reference)

        missing_fields = []

        for field in (
            "document_id",
            "clause_id",
            "page_number",
            "char_start",
            "char_end",
        ):
            if provenance.get(field) is None:
                missing_fields.append(field)

        if missing_fields:
            unresolved_questions.append(
                f"Evidence {evidence_id} has incomplete provenance: "
                f"{', '.join(missing_fields)}."
            )

    @staticmethod
    def _collect_uncertainties(
        obligation: dict,
        context: dict,
        unresolved_questions: list,
    ) -> None:
        evidence_id = obligation.get("evidence_id", "unknown")

        verification_status = obligation.get("verification_status")

        if verification_status != "verified":
            unresolved_questions.append(
                f"Evidence {evidence_id} is not verified."
            )

        trigger = context.get("trigger", {})
        responsibility = context.get("responsibility", {})
        recipient = context.get("recipient", {})

        if trigger.get("trigger_type") in (
            "unspecified",
            "multiple_or_ambiguous",
        ):
            unresolved_questions.append(
                f"Evidence {evidence_id} has an unspecified or ambiguous trigger."
            )

        if responsibility.get("party_confidence") != "rule_based":
            unresolved_questions.append(
                f"Evidence {evidence_id} has an unknown or ambiguous responsible party."
            )

        if recipient.get("direction") in (
            "unspecified",
            "ambiguous",
        ):
            unresolved_questions.append(
                f"Evidence {evidence_id} has an unspecified or ambiguous recipient direction."
            )

    def _failure(self, code: str, message: str) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Obligation analysis did not complete successfully.",
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )