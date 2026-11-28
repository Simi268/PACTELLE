from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.agents.contracts import AgentStatus, AgentTask
from app.agents.investigation_agent import InvestigationAgent
from app.agents.state import AgentState

from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.models.risk_event import RiskEvent
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence


class TrackingSession(Session):
    """SQLAlchemy session that records whether close() was called."""

    def close(self):
        self.was_closed = True
        super().close()


def make_state(organization_id=None, finding_id=None):
    task = AgentTask(
        organization_id=organization_id or uuid4(),
        task_type="risk_investigation",
        input_data={
            "risk_finding_id": str(finding_id or uuid4()),
        },
    )

    return AgentState(task=task)


def valid_investigation(finding_id):
    return {
        "risk_finding_id": str(finding_id),
        "risk_overview": {
            "title": "Renewal exposure",
            "severity": "high",
        },
        "investigation_summary": {
            "total_events": 0,
            "evidence_change_count": 0,
            "assessment_change_count": 0,
        },
        "timeline": [],
        "evidence_evolution": [],
        "assessment_evolution": [],
        "current_evidence": {
            "supporting": [],
            "rejected": [],
            "summary": {},
        },
        "unresolved_questions": [],
        "recommended_action": "Review the renewal provisions.",
        "human_review_required": False,
    }


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


def create_risk_finding(db_session, contract):
    finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description="The contract contains an automatic renewal provision.",
        severity="high",
        status="open",
        assessment_status="confirmed",
        detection_method="rule_based",
        rule_id=f"test-renewal-{uuid4()}",
        rule_version="1.0",
    )

    db_session.add(finding)
    db_session.flush()

    return finding


def create_event(
    db_session,
    finding,
    event_type,
    summary,
    created_at,
    evidence_snapshot=None,
    previous_state=None,
    new_state=None,
):
    event = RiskEvent(
        risk_finding_id=finding.id,
        contract_id=finding.contract_id,
        event_type=event_type,
        source="test",
        summary=summary,
        created_at=created_at,
        evidence_snapshot=evidence_snapshot,
        previous_state=previous_state,
        new_state=new_state,
    )

    db_session.add(event)
    db_session.flush()

    return event


def create_evidence(
    db_session,
    document,
    verification_status,
    evidence_text,
    clause_number="1",
):
    clause = ContractClause(
    document_id=document.id,
    clause_number=clause_number,
    clause_title="Renewal Terms",
    category="renewal",
    source_text=evidence_text,
    page_number=1,
    char_start=0,
    char_end=len(evidence_text),
    extraction_method="rule_based",
)

    db_session.add(clause)
    db_session.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Contract renewal provision",
        evidence_type="renewal_notice",
        evidence_text=evidence_text,
        page_number=1,
        char_start=10,
        char_end=10 + len(evidence_text),
        extraction_method="rule_based",
        confidence=None,
        verification_status=verification_status,
    )

    db_session.add(evidence)
    db_session.flush()

    return evidence


def test_investigation_agent_requires_finding_id():
    state = make_state()
    state.task.input_data = {}

    agent = InvestigationAgent()

    result = agent(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "MISSING_RISK_FINDING_ID"


def test_investigation_agent_validates_finding_id():
    state = make_state()
    state.task.input_data["risk_finding_id"] = "invalid-id"

    result = InvestigationAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_RISK_FINDING_ID"


def test_investigation_agent_rejects_missing_finding(
    db_session,
    contract_api_data,
):
    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
    )(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "RISK_FINDING_NOT_FOUND"
    assert sessions[0].was_closed is True


def test_investigation_agent_rejects_cross_organization_finding(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_b"],
    )

    create_session, sessions = make_tracking_factory(db_session)

    service_called = False

    def investigation_service(finding, events):
        nonlocal service_called
        service_called = True
        return valid_investigation(finding.id)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
        investigation_service=investigation_service,
    )(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "RISK_FINDING_NOT_FOUND"

    # A cross-organization finding must never reach the investigation service.
    assert service_called is False
    assert sessions[0].was_closed is True


def test_investigation_agent_reconstructs_events_chronologically(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    later_event = create_event(
        db_session,
        finding,
        "status_changed",
        "Finding acknowledged",
        base_time + timedelta(days=2),
        previous_state={"status": "open"},
        new_state={"status": "acknowledged"},
    )

    earlier_event = create_event(
        db_session,
        finding,
        "risk_created",
        "Risk finding created",
        base_time,
    )

    received_event_ids = []

    def investigation_service(received_finding, events):
        received_event_ids.extend(
            event.id for event in events
        )
        return valid_investigation(received_finding.id)

    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
        investigation_service=investigation_service,
    )(state)

    assert result.status == AgentStatus.COMPLETED

    assert received_event_ids == [
        earlier_event.id,
        later_event.id,
    ]

    assert sessions[0].was_closed is True


def test_investigation_agent_preserves_historical_evidence_changes(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    old_evidence = {
        "evidence_type": "renewal_notice",
        "claim": "Notice period is 60 days.",
        "evidence_text": "The customer must provide 60 days' notice.",
        "verification_status": "unverified",
    }

    new_evidence = {
        "evidence_type": "renewal_notice",
        "claim": "Notice period is 90 days.",
        "evidence_text": "The customer must provide 90 days' notice.",
        "verification_status": "rejected",
    }

    event = create_event(
        db_session,
        finding,
        "evidence_changed",
        "Renewal evidence changed",
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        evidence_snapshot={
            "previous": [old_evidence],
            "current": [new_evidence],
        },
    )

    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
    )(state)

    assert result.status == AgentStatus.COMPLETED

    evolution = result.data["evidence_evolution"]

    assert len(evolution) == 1
    assert evolution[0]["event_id"] == str(event.id)

    assert evolution[0]["removed"] == [old_evidence]
    assert evolution[0]["added"] == [new_evidence]

    # Historical verification states must remain unchanged.
    assert evolution[0]["removed"][0]["verification_status"] == "unverified"
    assert evolution[0]["added"][0]["verification_status"] == "rejected"

    assert sessions[0].was_closed is True


def test_investigation_agent_collects_current_evidence_provenance(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    unverified = create_evidence(
    db_session,
    contract_api_data["document_a"],
    "unverified",
    "The customer must provide 60 days' notice.",
    clause_number="1",
)

    rejected = create_evidence(
    db_session,
    contract_api_data["document_a"],
    "rejected",
    "An earlier extracted renewal statement.",
    clause_number="2",
)

    db_session.add_all([
        RiskFindingEvidence(
            risk_finding_id=finding.id,
            evidence_record_id=unverified.id,
        ),
        RiskFindingEvidence(
            risk_finding_id=finding.id,
            evidence_record_id=rejected.id,
        ),
    ])
    db_session.flush()

    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
    )(state)

    assert result.status == AgentStatus.COMPLETED

    references = {
        reference.evidence_id: reference
        for reference in result.evidence_references
    }

    assert str(unverified.id) in references
    assert str(rejected.id) in references

    assert (
        references[str(unverified.id)].verification_status
        == "unverified"
    )
    assert (
        references[str(rejected.id)].verification_status
        == "rejected"
    )

    assert references[str(unverified.id)].document_id == str(
        contract_api_data["document_a"].id
    )

    assert references[str(unverified.id)].page_number == 1
    assert references[str(unverified.id)].char_start == 10
    assert references[str(unverified.id)].char_end is not None

    assert sessions[0].was_closed is True


def test_investigation_agent_marks_human_review_when_uncertain(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    investigation = valid_investigation(finding.id)
    investigation["unresolved_questions"] = [
        "Historical evidence verification is incomplete."
    ]

    investigation["human_review_required"] = False

    create_session, _ = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
        investigation_service=lambda finding, events: investigation,
    )(state)

    assert result.status == AgentStatus.COMPLETED
    assert result.human_review_required is True
    assert len(result.unresolved_questions) == 1


def test_investigation_agent_rejects_invalid_service_output(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
        investigation_service=lambda finding, events: {},
    )(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INCOMPLETE_INVESTIGATION_RESULT"
    assert "risk_finding_id" in result.data["missing_fields"]
    assert sessions[0].was_closed is True


def test_investigation_agent_does_not_mutate_database(
    db_session,
    contract_api_data,
):
    finding = create_risk_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_event(
        db_session,
        finding,
        "risk_created",
        "Risk finding created",
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    def count_rows(model):
        return db_session.query(func.count(model.id)).scalar()

    before = {
        "findings": count_rows(RiskFinding),
        "events": count_rows(RiskEvent),
        "evidence": count_rows(EvidenceRecord),
    }

    create_session, sessions = make_tracking_factory(db_session)

    state = make_state(
        organization_id=contract_api_data["organization_a"].id,
        finding_id=finding.id,
    )

    result = InvestigationAgent(
        session_factory=create_session,
    )(state)

    after = {
        "findings": count_rows(RiskFinding),
        "events": count_rows(RiskEvent),
        "evidence": count_rows(EvidenceRecord),
    }

    assert result.status == AgentStatus.COMPLETED
    assert after == before
    assert sessions[0].was_closed is True