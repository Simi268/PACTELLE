"""Orchestration entry point for organization-level intelligence analysis."""

import logging
from uuid import UUID

from app.agents.contracts import AgentTask
from app.agents.obligation_agent import ObligationAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.orchestration.supervisor import Supervisor

from app.agents.verification_agent import VerificationAgent

logger = logging.getLogger(__name__)


def run_organization_obligation_analysis(
    organization_id: UUID,
    requested_by_user_id: UUID | None = None,
) -> dict:
    """Run organization-level obligation and intelligence analysis.

    Execution sequence:
        1. Obligation Agent retrieves and analyzes current evidence.
        2. Intelligence Agent analyzes normalized obligations.

    Both agents share the same execution state through Supervisor.
    """

    task = AgentTask(
        organization_id=organization_id,
        task_type="organization_obligation_analysis",
        requested_by_user_id=requested_by_user_id,
        input_data={
            "organization_id": str(organization_id),
        },
    )

    supervisor = Supervisor(
    handlers=[
        ObligationAgent(),
        VerificationAgent(),
        IntelligenceAgent(),
    ]
)

    state = supervisor.run(task)

    logger.info(
        "Organization intelligence execution finished: "
        "execution_id=%s organization_id=%s status=%s",
        state.execution_id,
        organization_id,
        state.status.value,
    )

    agent_results = {
        name: result.model_dump(mode="json")
        for name, result in state.results.items()
    }

    return {
        "execution_id": str(state.execution_id),
        "organization_id": str(organization_id),
        "status": state.status.value,
        "human_review_required": state.human_review_required,
        "unresolved_questions": state.unresolved_questions,
        "errors": [
            error.model_dump(mode="json")
            for error in state.errors
        ],
        "agent_results": agent_results,
        "gate_decisions": state.gate_decisions,
        "execution_trace": [
            record.model_dump(mode="json")
            for record in state.execution_trace
        ],
        "obligation_result": agent_results.get("obligation"),
        "intelligence_result": agent_results.get("intelligence"),
    }