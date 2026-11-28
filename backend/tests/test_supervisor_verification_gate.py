from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
    ExecutionStatus,
)
from app.orchestration.supervisor import Supervisor


EVIDENCE_ID = str(uuid4())


def make_task():
    return AgentTask(
        organization_id=uuid4(),
        task_type="organization_obligation_analysis",
    )


def make_obligation_agent():
    def handler(state):
        return AgentResult(
            agent=AgentName.OBLIGATION,
            status=AgentStatus.COMPLETED,
            data={
                "obligations": [
                    {"evidence_id": EVIDENCE_ID}
                ],
                "excluded_obligations": [],
            },
        )

    handler.agent_name = AgentName.OBLIGATION
    return handler


def make_verification_agent(outcome="verified"):
    def handler(state):
        checks = {
            "document_exists": True,
            "clause_exists": True,
            "document_matches": True,
            "page_matches": True,
            "offsets_valid": True,
            "source_text_matches": True,
        }

        return AgentResult(
            agent=AgentName.VERIFICATION,
            status=AgentStatus.COMPLETED,
            data={
                "total": 1,
                "verified": int(outcome == "verified"),
                "unverified": int(outcome == "unverified"),
                "review_required": int(outcome == "review_required"),
                "results": [
                    {
                        "evidence_id": EVIDENCE_ID,
                        "outcome": outcome,
                        "stored_verification_status": (
                            "verified"
                            if outcome == "verified"
                            else outcome
                        ),
                        "checks": checks,
                    }
                ],
            },
        )

    handler.agent_name = AgentName.VERIFICATION
    return handler


def make_intelligence_agent(executed):
    def handler(state):
        executed.append(True)

        return AgentResult(
            agent=AgentName.INTELLIGENCE,
            status=AgentStatus.COMPLETED,
            data={"comparisons": []},
        )

    handler.agent_name = AgentName.INTELLIGENCE
    return handler


def test_supervisor_runs_intelligence_after_approved_verification():
    executed = []

    supervisor = Supervisor([
        make_obligation_agent(),
        make_verification_agent("verified"),
        make_intelligence_agent(executed),
    ])

    state = supervisor.run(make_task())

    assert state.status == ExecutionStatus.COMPLETED
    assert executed == [True]

    assert state.gate_decisions[
        "evidence_verification"
    ]["passed"] is True


def test_supervisor_blocks_intelligence_for_unverified_evidence():
    executed = []

    supervisor = Supervisor([
        make_obligation_agent(),
        make_verification_agent("unverified"),
        make_intelligence_agent(executed),
    ])

    state = supervisor.run(make_task())

    assert state.status == ExecutionStatus.REVIEW_REQUIRED
    assert executed == []
    assert state.human_review_required is True

    assert state.gate_decisions[
        "evidence_verification"
    ]["passed"] is False


def test_supervisor_blocks_intelligence_for_invalid_provenance():
    executed = []

    def invalid_verification(state):
        return AgentResult(
            agent=AgentName.VERIFICATION,
            status=AgentStatus.COMPLETED,
            data={
                "results": [
                    {
                        "evidence_id": EVIDENCE_ID,
                        "outcome": "verified",
                        "stored_verification_status": "verified",
                        "checks": {
                            "source_text_matches": False,
                        },
                    }
                ]
            },
        )

    invalid_verification.agent_name = AgentName.VERIFICATION

    supervisor = Supervisor([
        make_obligation_agent(),
        invalid_verification,
        make_intelligence_agent(executed),
    ])

    state = supervisor.run(make_task())

    assert state.status == ExecutionStatus.REVIEW_REQUIRED
    assert executed == []


def test_supervisor_stops_if_verification_agent_fails():
    executed = []

    def failed_verification(state):
        from app.agents.contracts import AgentError

        return AgentResult(
            agent=AgentName.VERIFICATION,
            status=AgentStatus.FAILED,
            error=AgentError(
                agent=AgentName.VERIFICATION,
                code="TEST_FAILURE",
                message="Verification failed.",
                retryable=False,
            ),
        )

    failed_verification.agent_name = AgentName.VERIFICATION

    supervisor = Supervisor([
        make_obligation_agent(),
        failed_verification,
        make_intelligence_agent(executed),
    ])

    state = supervisor.run(make_task())

    assert state.status == ExecutionStatus.FAILED
    assert executed == []