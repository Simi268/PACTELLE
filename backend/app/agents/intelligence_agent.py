"""Intelligence Agent for PACTELLE.

Coordinates existing deterministic portfolio intelligence.
Consumes normalized obligations from the Obligation Agent.
Does not independently retrieve evidence or modify database records.
"""

import logging
from typing import Callable, Optional

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
)
from app.agents.state import AgentState
from app.services.portfolio_intelligence_engine import (
    analyze_organization_portfolio,
)

logger = logging.getLogger(__name__)


class IntelligenceAgent:
    agent_name = AgentName.INTELLIGENCE

    def __init__(
        self,
        intelligence_engine: Optional[Callable] = None,
    ):
        self.intelligence_engine = (
            intelligence_engine or analyze_organization_portfolio
        )

    def __call__(self, state: AgentState) -> AgentResult:
        try:
            obligation_result = state.results.get("obligation")

            if obligation_result is None:
                return self._failure(
                    "OBLIGATION_RESULT_MISSING",
                    "Intelligence analysis requires a completed "
                    "Obligation Agent result.",
                )

            if obligation_result.status != AgentStatus.COMPLETED:
                return self._failure(
                    "OBLIGATION_RESULT_NOT_COMPLETED",
                    "The preceding Obligation Agent did not complete successfully.",
                )

            obligations = obligation_result.data.get("obligations")

            if not isinstance(obligations, list):
                return self._failure(
                    "INVALID_OBLIGATION_INPUT",
                    "The Obligation Agent did not provide a valid obligation list.",
                )

            intelligence = self.intelligence_engine(obligations)

            if not isinstance(intelligence, dict):
                return self._failure(
                    "INVALID_INTELLIGENCE_OUTPUT",
                    "The intelligence engine returned an invalid response.",
                )

            comparisons = intelligence.get("comparisons", [])

            if not isinstance(comparisons, list):
                return self._failure(
                    "INVALID_COMPARISON_OUTPUT",
                    "The intelligence engine returned invalid comparisons.",
                )

            # Fail closed if the existing engine ever violates
            # PACTELLE's legal-conflict safety invariant.
            for comparison in comparisons:
                if (
                    not isinstance(comparison, dict)
                    or comparison.get("legal_conflict_established") is not False
                ):
                    logger.error(
                        "Intelligence engine violated legal-conflict invariant."
                    )

                    return self._failure(
                        "LEGAL_CONFLICT_INVARIANT_VIOLATION",
                        "Intelligence output failed legal-conflict safety "
                        "validation. Results were not accepted.",
                    )

            summary = intelligence.get("summary", {})

            if not isinstance(summary, dict):
                return self._failure(
                    "INVALID_INTELLIGENCE_SUMMARY",
                    "The intelligence engine returned an invalid summary.",
                )

            review_queue = intelligence.get("human_review_queue", [])

            if not isinstance(review_queue, list):
                return self._failure(
                    "INVALID_REVIEW_QUEUE",
                    "The intelligence engine returned an invalid review queue.",
                )

            review_required = bool(
                review_queue
                or summary.get("human_review_required", 0)
            )

            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary=(
                    f"Analyzed {summary.get('eligible_obligations', 0)} "
                    f"eligible obligations and generated "
                    f"{summary.get('total_comparisons', 0)} comparisons."
                ),
                data={
                    "organization_id": str(state.organization_id),
                    "summary": summary,
                    "comparisons": comparisons,
                    "human_review_queue": review_queue,
                    "context_summary": intelligence.get(
                        "context_summary", {}
                    ),
                    "comparison_summary": intelligence.get(
                        "comparison_summary", {}
                    ),
                },
                human_review_required=review_required,
            )

        except Exception:
            logger.exception(
                "Intelligence Agent failed for organization %s",
                state.organization_id,
            )

            return self._failure(
                "INTELLIGENCE_ANALYSIS_FAILED",
                "Portfolio intelligence analysis failed. "
                "No successful analysis is assumed.",
            )

    def _failure(self, code: str, message: str) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Intelligence analysis did not complete successfully.",
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )