from uuid import uuid4

import pytest

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.agents.contracts import AgentStatus, AgentTask
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.state import AgentState

from app.models.portfolio_risk_finding import PortfolioRiskFinding


class TrackingSession(Session):

    def close(self):
        self.was_closed = True
        super().close()


def make_state(organization_id=None, finding_id=None):
    task = AgentTask(
        organization_id=organization_id or uuid4(),
        task_type="recommendation_generation",
        input_data={
            "portfolio_finding_id": (
                str(finding_id) if finding_id else None
            )
        },
    )

    return AgentState(task=task)


def make_tracking_factory(db_session):
    connection = db_session.connection()
    created_sessions = []

    factory = sessionmaker(
        bind=connection,
        class_=TrackingSession,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def create_session():
        session = factory()
        created_sessions.append(session)
        return session

    return create_session, created_sessions


def create_finding(
    db_session,
    organization_id,
    finding_type="potential_conflict",
    severity="high",
    assessment_status="confirmed",
):
    finding = PortfolioRiskFinding(
        organization_id=organization_id,
        finding_type=finding_type,
        title="Potential Contractual Dependency",
        description="Related contractual obligations require review.",
        severity=severity,
        status="open",
        assessment_status=assessment_status,
        detection_method="rule_based",
        rule_id=f"test-recommendation-{uuid4()}",
        rule_version="1.0",
        confidence=None,
        details={
            "legal_conflict_established": False,
            "requires_human_review": True,
        },
    )

    db_session.add(finding)
    db_session.flush()

    return finding


def run_agent(db_session, state, recommendation_service=None):
    create_session, sessions = make_tracking_factory(db_session)

    kwargs = {
        "session_factory": create_session,
    }

    if recommendation_service is not None:
        kwargs["recommendation_service"] = recommendation_service

    result = RecommendationAgent(**kwargs)(state)

    return result, sessions


def test_recommendation_agent_requires_finding_id():
    state = make_state()

    result = RecommendationAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "MISSING_PORTFOLIO_FINDING_ID"


def test_recommendation_agent_validates_finding_id():
    state = make_state()
    state.task.input_data["portfolio_finding_id"] = "invalid-id"

    result = RecommendationAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_PORTFOLIO_FINDING_ID"


def test_recommendation_agent_rejects_missing_finding(
    db_session,
    contract_api_data,
):
    state = make_state(
        contract_api_data["organization_a"].id,
        uuid4(),
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "PORTFOLIO_FINDING_NOT_FOUND"
    assert sessions[0].was_closed is True


def test_recommendation_agent_rejects_cross_organization_finding(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_b"].id,
    )

    service_called = False

    def recommendation_service(finding):
        nonlocal service_called
        service_called = True
        return []

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, sessions = run_agent(
        db_session,
        state,
        recommendation_service,
    )

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "PORTFOLIO_FINDING_NOT_FOUND"

    assert service_called is False
    assert sessions[0].was_closed is True


def test_recommendation_agent_generates_conflict_recommendations(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
        finding_type="potential_conflict",
        severity="high",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED

    assert result.data["portfolio_finding_id"] == str(finding.id)
    assert result.data["recommendation_count"] == 2

    recommendations = result.data["recommendations"]

    assert len(recommendations) == 2

    for recommendation in recommendations:
        assert recommendation["requires_human_review"] is True
        assert recommendation["legal_conclusion"] is False
        assert recommendation["priority"] == "high"
        assert recommendation["due_days"] == 7

    assert result.human_review_required is True
    assert result.data["execution_performed"] is False
    assert result.data["database_mutation_performed"] is False
    assert result.data["legal_conclusions_established"] is False

    assert sessions[0].was_closed is True


def test_recommendation_agent_preserves_provisional_uncertainty(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
        assessment_status="provisional",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, _ = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED

    assert result.data["finding_assessment_status"] == "provisional"

    assert any(
        "provisional" in question.lower()
        for question in result.unresolved_questions
    )

    recommendation = result.data["recommendations"][0]

    assert "provisional" in recommendation["rationale"].lower()
    assert result.human_review_required is True


def test_recommendation_agent_uses_severity_for_priority(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
        severity="critical",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, _ = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED

    for recommendation in result.data["recommendations"]:
        assert recommendation["priority"] == "critical"
        assert recommendation["due_days"] == 2


def test_recommendation_agent_handles_no_available_template(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, sessions = run_agent(
        db_session,
        state,
        recommendation_service=lambda finding: [],
    )

    assert result.status == AgentStatus.COMPLETED
    assert result.data["recommendation_count"] == 0

    assert any(
        "no recommendation template" in question.lower()
        for question in result.unresolved_questions
    )

    assert result.human_review_required is True
    assert sessions[0].was_closed is True


def test_recommendation_agent_rejects_invalid_service_output(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, sessions = run_agent(
        db_session,
        state,
        recommendation_service=lambda finding: None,
    )

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_RECOMMENDATION_OUTPUT"

    assert sessions[0].was_closed is True


def test_recommendation_agent_enforces_human_review(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    invalid_recommendation = {
        "title": "Execute action",
        "description": "Execute without review.",
        "rationale": "Unsafe recommendation.",
        "priority": "high",
        "due_days": 7,
        "requires_human_review": False,
        "legal_conclusion": False,
    }

    result, _ = run_agent(
        db_session,
        state,
        recommendation_service=lambda finding: [
            invalid_recommendation
        ],
    )

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "HUMAN_REVIEW_INVARIANT_VIOLATION"


def test_recommendation_agent_rejects_legal_conclusion(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    invalid_recommendation = {
        "title": "Legal conclusion",
        "description": "A conflict is legally established.",
        "rationale": "Unsafe.",
        "priority": "high",
        "due_days": 7,
        "requires_human_review": True,
        "legal_conclusion": True,
    }

    result, _ = run_agent(
        db_session,
        state,
        recommendation_service=lambda finding: [
            invalid_recommendation
        ],
    )

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "LEGAL_CONCLUSION_INVARIANT_VIOLATION"


def test_recommendation_agent_rejects_incomplete_recommendation(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, _ = run_agent(
        db_session,
        state,
        recommendation_service=lambda finding: [
            {"title": "Incomplete recommendation"}
        ],
    )

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INCOMPLETE_RECOMMENDATION"


def test_recommendation_agent_does_not_mutate_database(
    db_session,
    contract_api_data,
):
    finding = create_finding(
        db_session,
        contract_api_data["organization_a"].id,
    )

    before = db_session.query(
        func.count(PortfolioRiskFinding.id)
    ).scalar()

    original_status = finding.status

    state = make_state(
        contract_api_data["organization_a"].id,
        finding.id,
    )

    result, sessions = run_agent(db_session, state)

    after = db_session.query(
        func.count(PortfolioRiskFinding.id)
    ).scalar()

    db_session.refresh(finding)

    assert result.status == AgentStatus.COMPLETED
    assert before == after
    assert finding.status == original_status

    assert sessions[0].was_closed is True