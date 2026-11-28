from uuid import uuid4

from app.agents.contracts import (
    AgentName,
    AgentStatus,
    AgentTask,
)
from app.agents.state import AgentState
from app.agents.obligation_agent import ObligationAgent


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def make_obligation(
    verification_status="verified",
    trigger_type="subprocessor_change",
    party_confidence="rule_based",
):
    return {
        "evidence_id": str(uuid4()),
        "contract_id": str(uuid4()),
        "obligation_type": "subprocessor_change_notice",
        "obligation_family": "subprocessors",
        "claim": "Vendor shall notify Customer before changing subprocessors.",
        "original_text": "Vendor shall notify Customer before changing subprocessors.",
        "verification_status": verification_status,
        "provenance": {
            "document_id": str(uuid4()),
            "clause_id": str(uuid4()),
            "page_number": 2,
            "char_start": 100,
            "char_end": 160,
        },
        "context": {
            "trigger_type": trigger_type,
            "party_confidence": party_confidence,
        },
    }


def make_context(obligation):
    return {
        "evidence_id": obligation["evidence_id"],
        "trigger": {
            "trigger_type": obligation["context"]["trigger_type"],
        },
        "responsibility": {
            "responsible_party": "vendor",
            "party_confidence": obligation["context"]["party_confidence"],
        },
        "recipient": {
            "recipient_party": "customer",
            "direction": "vendor_to_customer",
        },
        "context_confidence": "rule_based",
    }


def make_state():
    return AgentState(
        task=AgentTask(
            organization_id=uuid4(),
            task_type="obligation_analysis",
        )
    )


def make_agent(retrieval):
    session = FakeSession()

    agent = ObligationAgent(
        session_factory=lambda: session,
        retriever=lambda db, organization_id: retrieval,
        context_analyzer=make_context,
    )

    return agent, session


def test_obligation_agent_processes_verified_obligation():
    obligation = make_obligation()

    agent, session = make_agent({
        "summary": {
            "contracts_with_obligations": 1,
            "unsupported_evidence": 0,
        },
        "obligations": [obligation],
        "excluded_obligations": [],
        "grouped_by_family": {},
        "grouped_by_type": {},
    })

    result = agent(make_state())

    assert result.agent == AgentName.OBLIGATION
    assert result.status == AgentStatus.COMPLETED
    assert len(result.data["obligations"]) == 1
    assert result.data["obligations"][0]["context_analysis"]
    assert session.closed is True


def test_obligation_agent_preserves_unverified_status():
    obligation = make_obligation(verification_status="unverified")

    agent, _ = make_agent({
        "summary": {},
        "obligations": [obligation],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert result.data["obligations"][0]["verification_status"] == "unverified"
    assert result.human_review_required is True
    assert any("not verified" in q for q in result.unresolved_questions)


def test_obligation_agent_flags_ambiguous_trigger():
    obligation = make_obligation(
        trigger_type="multiple_or_ambiguous"
    )

    agent, _ = make_agent({
        "summary": {},
        "obligations": [obligation],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert result.human_review_required is True
    assert any("ambiguous trigger" in q for q in result.unresolved_questions)


def test_obligation_agent_flags_unknown_responsible_party():
    obligation = make_obligation(
        party_confidence="unknown"
    )

    agent, _ = make_agent({
        "summary": {},
        "obligations": [obligation],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert result.human_review_required is True
    assert any("responsible party" in q for q in result.unresolved_questions)


def test_obligation_agent_flags_missing_provenance():
    obligation = make_obligation()
    obligation["provenance"]["page_number"] = None
    obligation["provenance"]["char_start"] = None

    agent, _ = make_agent({
        "summary": {},
        "obligations": [obligation],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert result.human_review_required is True
    assert any("incomplete provenance" in q for q in result.unresolved_questions)


def test_obligation_agent_keeps_rejected_evidence_separate():
    rejected = make_obligation(verification_status="rejected")

    agent, _ = make_agent({
        "summary": {},
        "obligations": [],
        "excluded_obligations": [rejected],
    })

    result = agent(make_state())

    assert result.data["obligations"] == []
    assert len(result.data["excluded_obligations"]) == 1
    assert result.data["excluded_obligations"][0]["verification_status"] == "rejected"


def test_obligation_agent_handles_empty_results():
    agent, _ = make_agent({
        "summary": {
            "unsupported_evidence": 0,
        },
        "obligations": [],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert result.status == AgentStatus.COMPLETED
    assert result.data["obligations"] == []
    assert result.human_review_required is True


def test_obligation_agent_reports_unsupported_evidence():
    agent, _ = make_agent({
        "summary": {
            "unsupported_evidence": 3,
        },
        "obligations": [],
        "excluded_obligations": [],
    })

    result = agent(make_state())

    assert any(
        "3 evidence records" in q
        for q in result.unresolved_questions
    )


def test_obligation_agent_handles_retrieval_failure():
    session = FakeSession()

    def failing_retriever(db, organization_id):
        raise RuntimeError("Database unavailable")

    agent = ObligationAgent(
        session_factory=lambda: session,
        retriever=failing_retriever,
    )

    result = agent(make_state())

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "OBLIGATION_ANALYSIS_FAILED"
    assert session.closed is True