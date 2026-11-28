from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentResult,
    AgentStatus,
)
from app.orchestration.execution_status import ExecutionStatus
from app.orchestration import obligation_analysis_runner
from app.agents.contracts import AgentName


class FakeSupervisor:
    received_task = None
    received_handlers = None

    def __init__(self, handlers):
        FakeSupervisor.received_handlers = handlers

    def run(self, task):
        FakeSupervisor.received_task = task

        from app.agents.state import AgentState

        state = AgentState(task=task)
        state.status = ExecutionStatus.COMPLETED

        obligation_result = AgentResult(
            agent=AgentName.OBLIGATION,
            status=AgentStatus.COMPLETED,
            summary="Obligations retrieved.",
            data={"obligations": []},
        )

        state.add_result(obligation_result)

        intelligence_result = AgentResult(
            agent=AgentName.INTELLIGENCE,
            status=AgentStatus.COMPLETED,
            summary="Intelligence analysis completed.",
            data={"comparisons": []},
        )

        state.add_result(intelligence_result)

        return state


def test_runner_creates_organization_scoped_execution(monkeypatch):
    monkeypatch.setattr(
        obligation_analysis_runner,
        "Supervisor",
        FakeSupervisor,
    )

    organization_id = uuid4()
    user_id = uuid4()

    result = (
        obligation_analysis_runner.run_organization_obligation_analysis(
            organization_id=organization_id,
            requested_by_user_id=user_id,
        )
    )

    task = FakeSupervisor.received_task

    assert task.organization_id == organization_id
    assert task.requested_by_user_id == user_id
    assert task.task_type == "organization_obligation_analysis"

    assert task.input_data["organization_id"] == str(organization_id)

    assert result["organization_id"] == str(organization_id)
    assert result["status"] == "completed"


def test_runner_registers_agents_in_correct_order(monkeypatch):
    monkeypatch.setattr(
        obligation_analysis_runner,
        "Supervisor",
        FakeSupervisor,
    )

    obligation_analysis_runner.run_organization_obligation_analysis(
        organization_id=uuid4(),
    )

    handlers = FakeSupervisor.received_handlers
    assert len(handlers) == 3
    assert handlers[0].agent_name == AgentName.OBLIGATION
    assert handlers[1].agent_name == AgentName.VERIFICATION
    assert handlers[2].agent_name == AgentName.INTELLIGENCE


def test_runner_returns_both_agent_results(monkeypatch):
    monkeypatch.setattr(
        obligation_analysis_runner,
        "Supervisor",
        FakeSupervisor,
    )

    result = (
        obligation_analysis_runner.run_organization_obligation_analysis(
            organization_id=uuid4(),
        )
    )

    assert result["obligation_result"] is not None
    assert result["intelligence_result"] is not None

    assert "obligation" in result["agent_results"]
    assert "intelligence" in result["agent_results"]


def test_runner_preserves_human_review_status(monkeypatch):
    class ReviewSupervisor(FakeSupervisor):
        def run(self, task):
            from app.agents.state import AgentState

            state = AgentState(task=task)
            state.status = ExecutionStatus.REVIEW_REQUIRED
            state.human_review_required = True

            state.unresolved_questions = [
                "Evidence provenance requires review."
            ]

            return state

    monkeypatch.setattr(
        obligation_analysis_runner,
        "Supervisor",
        ReviewSupervisor,
    )

    result = (
        obligation_analysis_runner.run_organization_obligation_analysis(
            organization_id=uuid4(),
        )
    )

    assert result["status"] == "review_required"
    assert result["human_review_required"] is True

    assert (
        "Evidence provenance requires review."
        in result["unresolved_questions"]
    )