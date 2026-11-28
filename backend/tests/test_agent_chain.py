from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentTask,
)
from app.agents.state import AgentState
from app.agents.obligation_agent import ObligationAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.orchestration.supervisor import Supervisor


class FakeSession:
    def close(self):
        pass


def make_obligation():
    return {
        "evidence_id": str(uuid4()),
        "contract_id": str(uuid4()),
        "contract_title": "Vendor Agreement",
        "obligation_type": "subprocessor_change_notice",
        "obligation_family": "data_protection",
        "claim": "Vendor shall notify Customer 90 days before changing subprocessors.",
        "original_text": "Vendor shall notify Customer 90 days before changing subprocessors.",
        "duration": {
            "value": 90,
            "unit": "days",
        },
        "verification_status": "verified",
        "analysis_eligible": True,
        "provenance": {
            "document_id": str(uuid4()),
            "clause_id": str(uuid4()),
            "page_number": 1,
            "char_start": 10,
            "char_end": 100,
        },
    }


def test_obligation_and_intelligence_agents_execute_in_sequence():
    first = make_obligation()
    second = make_obligation()

    def retriever(db, organization_id):
        return {
            "summary": {
                "contracts_with_obligations": 2,
                "unsupported_evidence": 0,
            },
            "obligations": [first, second],
            "excluded_obligations": [],
            "grouped_by_family": {},
            "grouped_by_type": {},
        }

    obligation_agent = ObligationAgent(
        session_factory=FakeSession,
        retriever=retriever,
    )

    intelligence_agent = IntelligenceAgent()

    supervisor = Supervisor(
        handlers=[
            obligation_agent,
            intelligence_agent,
        ]
    )

    task = AgentTask(
        organization_id=uuid4(),
        task_type="organization_obligation_analysis",
    )

    state = supervisor.run(task)

    assert state.status.value in {
        "completed",
        "review_required",
    }

    assert "obligation" in state.results
    assert "intelligence" in state.results

    assert (
        state.results["obligation"].agent
        == AgentName.OBLIGATION
    )

    assert (
        state.results["intelligence"].agent
        == AgentName.INTELLIGENCE
    )

    assert state.results["intelligence"].data["summary"][
        "total_comparisons"
    ] == 1

    for comparison in state.results["intelligence"].data["comparisons"]:
        assert comparison["legal_conflict_established"] is False


def test_supervisor_stops_if_obligation_agent_fails():
    def failing_retriever(db, organization_id):
        raise RuntimeError("Evidence retrieval failed")

    obligation_agent = ObligationAgent(
        session_factory=FakeSession,
        retriever=failing_retriever,
    )

    intelligence_agent = IntelligenceAgent()

    supervisor = Supervisor(
        handlers=[
            obligation_agent,
            intelligence_agent,
        ]
    )

    task = AgentTask(
        organization_id=uuid4(),
        task_type="organization_obligation_analysis",
    )

    state = supervisor.run(task)

    assert state.status.value == "failed"
    assert "obligation" in state.results
    assert "intelligence" not in state.results