"""Tests for PACTELLE's multi-agent foundation."""

from uuid import uuid4

import pytest

from app.agents.contracts import (
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
    ExecutionStatus,
)

from app.agents.state import AgentState

from app.orchestration.execution_status import transition_status
from app.orchestration.supervisor import Supervisor


def make_task():
    return AgentTask(
        organization_id=uuid4(),
        task_type="portfolio_analysis",
    )


def make_handler(
    agent_name,
    result_status=AgentStatus.COMPLETED,
    review=False,
):
    def handler(state):
        return AgentResult(
            agent=agent_name,
            status=result_status,
            summary="Test execution",
            human_review_required=review,
        )

    handler.agent_name = agent_name
    return handler


def test_agent_state_initialization():

    task = make_task()
    state = AgentState(task=task)

    assert state.status == ExecutionStatus.PENDING
    assert state.execution_id == task.execution_id
    assert state.organization_id == task.organization_id


def test_agent_state_tracks_human_review():

    state = AgentState(task=make_task())

    result = AgentResult(
        agent=AgentName.VERIFICATION,
        status=AgentStatus.COMPLETED,
        human_review_required=True,
        unresolved_questions=["Source page missing"],
    )

    state.add_result(result)

    assert state.human_review_required is True
    assert state.unresolved_questions == ["Source page missing"]


def test_failed_agent_result_requires_error():

    with pytest.raises(ValueError):

        AgentResult(
            agent=AgentName.DOCUMENT,
            status=AgentStatus.FAILED,
        )


def test_terminal_status_cannot_restart():

    with pytest.raises(ValueError):

        transition_status(
            ExecutionStatus.COMPLETED,
            ExecutionStatus.RUNNING,
        )


def test_supervisor_completes_successful_execution():

    supervisor = Supervisor([
        make_handler(AgentName.DOCUMENT),
        make_handler(AgentName.OBLIGATION),
    ])

    result = supervisor.run(make_task())

    assert result.status == ExecutionStatus.COMPLETED

    assert set(result.results) == {
        "document",
        "obligation",
    }

    assert result.current_agent is None
    assert result.completed_at is not None


def test_supervisor_requires_human_review():

    supervisor = Supervisor([
        make_handler(
            AgentName.VERIFICATION,
            review=True,
        ),
    ])

    result = supervisor.run(make_task())

    assert result.status == ExecutionStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


def test_supervisor_stops_after_agent_failure():

    supervisor = Supervisor([
        make_handler(AgentName.DOCUMENT),
        make_handler(
            AgentName.OBLIGATION,
            result_status=AgentStatus.FAILED,
        ),
        make_handler(AgentName.INTELLIGENCE),
    ])

    result = supervisor.run(make_task())

    assert result.status == ExecutionStatus.FAILED

    assert "document" in result.results
    assert "obligation" in result.results

    assert "intelligence" not in result.results


def test_supervisor_captures_unexpected_exception():

    def broken_handler(state):
        raise RuntimeError("Synthetic failure")

    broken_handler.agent_name = AgentName.DOCUMENT

    supervisor = Supervisor([broken_handler])

    result = supervisor.run(make_task())

    assert result.status == ExecutionStatus.FAILED

    assert result.errors[0].code == "AGENT_EXECUTION_ERROR"

    assert result.errors[0].message == "Synthetic failure"