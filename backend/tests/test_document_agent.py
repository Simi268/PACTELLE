from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentStatus,
    AgentTask,
    ExecutionStatus,
)
from app.agents.state import AgentState
from app.agents.document_agent import DocumentAgent
from app.orchestration.supervisor import Supervisor


def make_state():
    task = AgentTask(
        organization_id=uuid4(),
        task_type="document_processing",
        input_data={
            "document_id": str(uuid4()),
            "attempt_id": str(uuid4()),
        },
    )
    return AgentState(task=task)


def test_document_agent_successful_processing():

    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: {
            "document_id": str(document_id),
            "status": "completed",
            "text_units": 3,
            "clauses": 5,
            "evidence_records": 4,
        }
    )

    result = agent(make_state())

    assert result.status == AgentStatus.COMPLETED
    assert result.data["clauses"] == 5


def test_document_agent_ocr_required():

    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: {
            "document_id": str(document_id),
            "status": "needs_ocr",
        }
    )

    result = agent(make_state())

    assert result.status == AgentStatus.NEEDS_OCR
    assert result.human_review_required is True
    assert result.unresolved_questions


def test_document_agent_superseded_attempt():

    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: {
            "document_id": str(document_id),
            "status": "superseded",
        }
    )

    result = agent(make_state())

    assert result.status == AgentStatus.SUPERSEDED


def test_document_agent_pipeline_returns_none():

    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: None
    )

    result = agent(make_state())

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "DOCUMENT_PIPELINE_NO_RESULT"


def test_document_agent_rejects_invalid_document_id():

    state = make_state()
    state.task.input_data["document_id"] = "invalid-uuid"

    agent = DocumentAgent()

    result = agent(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_DOCUMENT_IDENTIFIER"


def test_document_agent_requires_attempt_id():

    state = make_state()
    state.task.input_data.pop("attempt_id")

    agent = DocumentAgent()

    result = agent(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_DOCUMENT_TASK"


def test_supervisor_handles_ocr_required_outcome():
    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: {
            "document_id": str(document_id),
            "status": "needs_ocr",
        }
    )

    result = Supervisor([agent]).run(make_state().task)

    assert result.status == ExecutionStatus.NEEDS_OCR
    assert result.human_review_required is True


def test_supervisor_stops_after_superseded_attempt():
    agent = DocumentAgent(
        pipeline=lambda document_id, attempt_id: {
            "document_id": str(document_id),
            "status": "superseded",
        }
    )

    result = Supervisor([agent]).run(make_state().task)

    assert result.status == ExecutionStatus.SUPERSEDED