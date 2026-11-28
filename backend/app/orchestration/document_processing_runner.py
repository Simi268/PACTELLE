"""Orchestration entry point for document processing."""

import logging
from uuid import UUID

from app.agents.contracts import AgentTask
from app.agents.document_agent import DocumentAgent
from app.orchestration.supervisor import Supervisor

logger = logging.getLogger(__name__)


def run_document_processing(
    document_id: UUID,
    attempt_id: UUID,
    organization_id: UUID,
) -> dict:
    """
    Execute document processing through the agent supervisor.

    The existing document pipeline remains responsible for
    extraction, database persistence and attempt validation.
    """

    task = AgentTask(
        organization_id=organization_id,
        task_type="document_processing",
        input_data={
            "document_id": str(document_id),
            "attempt_id": str(attempt_id),
        },
    )

    supervisor = Supervisor(
        handlers=[
            DocumentAgent(),
        ]
    )

    result = supervisor.run(task)

    logger.info(
        "Document agent execution finished: "
        "execution_id=%s document_id=%s status=%s",
        result.execution_id,
        document_id,
        result.status.value,
    )

    return {
        "execution_id": str(result.execution_id),
        "document_id": str(document_id),
        "status": result.status.value,
        "human_review_required": result.human_review_required,
        "unresolved_questions": result.unresolved_questions,
        "errors": [
            error.model_dump(mode="json")
            for error in result.errors
        ],
        "execution_trace": [
            record.model_dump(mode="json")
            for record in result.execution_trace
        ],
    }