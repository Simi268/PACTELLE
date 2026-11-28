from uuid import uuid4

import pytest

from app.agents.contracts import AgentName, AgentResult, AgentStatus, AgentTask, ExecutionStatus
from app.models.agent_execution import AgentExecution
from app.orchestration.supervisor import Supervisor
from app.services.agent_execution_service import get_execution, load_execution_state


class CompletedDocumentHandler:
    agent_name = AgentName.DOCUMENT

    def __call__(self, state):
        return AgentResult(
            agent=AgentName.DOCUMENT,
            status=AgentStatus.COMPLETED,
            summary="Document processing completed.",
        )


def test_persisted_supervisor_run_checkpoints_and_completes(db_session, contract_api_data):
    organization_id = contract_api_data["organization_a"].id
    requester_id = contract_api_data["owner_a"].id
    task = AgentTask(
        organization_id=organization_id,
        task_type="document_processing",
        requested_by_user_id=requester_id,
    )

    result = Supervisor([CompletedDocumentHandler()]).run_persisted(task, db_session)

    row = get_execution(
        db_session, organization_id=organization_id, execution_id=task.execution_id
    )
    restored = load_execution_state(row)

    assert result.status == ExecutionStatus.COMPLETED
    assert row.status == ExecutionStatus.COMPLETED.value
    assert row.next_agent_index == 1
    assert restored.results[AgentName.DOCUMENT.value].status == AgentStatus.COMPLETED
    assert len(restored.execution_trace) == 1
    assert restored.execution_trace[0].agent == AgentName.DOCUMENT


def test_persisted_supervisor_requires_requester_before_creating_execution(db_session, contract_api_data):
    task = AgentTask(
        organization_id=contract_api_data["organization_a"].id,
        task_type="document_processing",
    )

    with pytest.raises(ValueError, match="requested_by_user_id"):
        Supervisor([CompletedDocumentHandler()]).run_persisted(task, db_session)

    assert db_session.query(AgentExecution).filter(
        AgentExecution.execution_id == task.execution_id
    ).first() is None
