from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
)
from app.agents.state import AgentState
from app.agents.intelligence_agent import IntelligenceAgent


def make_obligation(
    duration_value=90,
    verification_status="verified",
    eligible=True,
):
    return {
        "evidence_id": str(uuid4()),
        "contract_id": str(uuid4()),
        "contract_title": "Vendor Agreement",
        "obligation_type": "subprocessor_change_notice",
        "obligation_family": "data_protection",
        "claim": (
            f"Vendor shall notify Customer "
            f"{duration_value} days before changing subprocessors."
        ),
        "original_text": (
            f"Vendor shall notify Customer "
            f"{duration_value} days before changing subprocessors."
        ),
        "duration": {
            "value": duration_value,
            "unit": "days",
        },
        "verification_status": verification_status,
        "analysis_eligible": eligible,
        "provenance": {
            "document_id": str(uuid4()),
            "clause_id": str(uuid4()),
            "page_number": 1,
            "char_start": 10,
            "char_end": 100,
        },
    }


def make_state(obligations):
    state = AgentState(
        task=AgentTask(
            organization_id=uuid4(),
            task_type="organization_intelligence_analysis",
        )
    )

    state.add_result(
        AgentResult(
            agent=AgentName.OBLIGATION,
            status=AgentStatus.COMPLETED,
            summary="Obligations retrieved.",
            data={
                "obligations": obligations,
                "excluded_obligations": [],
            },
        )
    )

    return state


def test_intelligence_agent_analyzes_obligations():
    first = make_obligation(90)
    second = make_obligation(30)

    agent = IntelligenceAgent()
    state = make_state([first, second])

    result = agent(state)

    assert result.status == AgentStatus.COMPLETED
    assert result.agent == AgentName.INTELLIGENCE
    assert result.data["summary"]["total_comparisons"] == 1


def test_intelligence_agent_identifies_contractual_variation():
    state = make_state([
        make_obligation(90),
        make_obligation(30),
    ])

    result = IntelligenceAgent()(state)

    comparison = result.data["comparisons"][0]

    assert comparison["classification"] == "contractual_variation"
    assert comparison["requires_human_review"] is True


def test_intelligence_agent_never_establishes_legal_conflict():
    state = make_state([
        make_obligation(90),
        make_obligation(30),
    ])

    result = IntelligenceAgent()(state)

    assert all(
        comparison["legal_conflict_established"] is False
        for comparison in result.data["comparisons"]
    )


def test_intelligence_agent_handles_similar_obligations():
    state = make_state([
        make_obligation(90),
        make_obligation(90),
    ])

    result = IntelligenceAgent()(state)

    assert result.status == AgentStatus.COMPLETED

    comparison = result.data["comparisons"][0]

    assert comparison["classification"] == "similar_obligation"
    assert comparison["legal_conflict_established"] is False


def test_intelligence_agent_handles_empty_obligations():
    state = make_state([])

    result = IntelligenceAgent()(state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["comparisons"] == []
    assert result.data["summary"]["total_comparisons"] == 0


def test_intelligence_agent_requires_obligation_result():
    state = AgentState(
        task=AgentTask(
            organization_id=uuid4(),
            task_type="organization_intelligence_analysis",
        )
    )

    result = IntelligenceAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "OBLIGATION_RESULT_MISSING"


def test_intelligence_agent_handles_engine_failure():
    def failing_engine(obligations):
        raise RuntimeError("Engine unavailable")

    state = make_state([make_obligation()])

    result = IntelligenceAgent(
        intelligence_engine=failing_engine
    )(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INTELLIGENCE_ANALYSIS_FAILED"


def test_intelligence_agent_rejects_legal_conflict_violation():
    def unsafe_engine(obligations):
        return {
            "summary": {},
            "comparisons": [
                {
                    "legal_conflict_established": True,
                }
            ],
            "human_review_queue": [],
        }

    state = make_state([make_obligation()])

    result = IntelligenceAgent(
        intelligence_engine=unsafe_engine
    )(state)

    assert result.status == AgentStatus.FAILED
    assert (
        result.error.code
        == "LEGAL_CONFLICT_INVARIANT_VIOLATION"
    )


def test_intelligence_agent_flags_human_review():
    state = make_state([
        make_obligation(90),
        make_obligation(30),
    ])

    result = IntelligenceAgent()(state)

    assert result.human_review_required is True