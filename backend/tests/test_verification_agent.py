from uuid import uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.agents.contracts import (
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
)
from app.agents.state import AgentState
from app.agents.verification_agent import VerificationAgent

from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord

from app.agents.contracts import AgentError


class TrackingSession(Session):
    """Session that records whether close() was called."""

    def close(self):
        self.was_closed = True
        super().close()


def make_state(organization_id=None):
    task = AgentTask(
        organization_id=organization_id or uuid4(),
        task_type="evidence_verification",
        input_data={},
    )
    return AgentState(task=task)


def add_obligation_result(
    state,
    obligations=None,
    excluded_obligations=None,
):
    result = AgentResult(
        agent=AgentName.OBLIGATION,
        status=AgentStatus.COMPLETED,
        summary="Obligation analysis completed.",
        data={
            "obligations": obligations or [],
            "excluded_obligations": excluded_obligations or [],
        },
    )
    state.add_result(result)


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


def create_evidence(
    db_session,
    document,
    verification_status="unverified",
    evidence_text="The customer must provide 60 days notice.",
    clause_number="1",
    clause_start=100,
    page_number=1,
):
    clause = ContractClause(
        document_id=document.id,
        clause_number=clause_number,
        clause_title="Renewal Terms",
        category="renewal",
        source_text=evidence_text,
        page_number=page_number,
        char_start=clause_start,
        char_end=clause_start + len(evidence_text),
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
        page_number=page_number,
        char_start=clause_start,
        char_end=clause_start + len(evidence_text),
        extraction_method="rule_based",
        confidence=None,
        verification_status=verification_status,
        is_current=True,
    )

    db_session.add(evidence)
    db_session.flush()

    return evidence, clause


def run_agent(db_session, state):
    create_session, sessions = make_tracking_factory(db_session)

    result = VerificationAgent(
        session_factory=create_session,
    )(state)

    return result, sessions


def test_verification_agent_requires_obligation_result():
    state = make_state()

    result = VerificationAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "MISSING_OBLIGATION_RESULT"


def test_verification_agent_rejects_incomplete_obligation_result():
    state = make_state()

    result = AgentResult(
        agent=AgentName.OBLIGATION,
        status=AgentStatus.FAILED,
        summary="Obligation analysis failed.",
        data={},
        error=AgentError(
            agent=AgentName.OBLIGATION,
            code="TEST_FAILURE",
            message="Simulated obligation agent failure.",
            retryable=False,
        ),
    )
    state.add_result(result)

    verification = VerificationAgent()(state)

    assert verification.status == AgentStatus.FAILED
    assert verification.error.code == "INVALID_OBLIGATION_RESULT"



def test_verification_agent_rejects_invalid_obligation_collections():
    state = make_state()

    result = AgentResult(
        agent=AgentName.OBLIGATION,
        status=AgentStatus.COMPLETED,
        summary="Completed.",
        data={
            "obligations": "not-a-list",
            "excluded_obligations": [],
        },
    )
    state.add_result(result)

    verification = VerificationAgent()(state)

    assert verification.status == AgentStatus.FAILED
    assert verification.error.code == "INVALID_OBLIGATION_COLLECTION"


def test_verification_agent_handles_no_evidence():
    state = make_state()
    add_obligation_result(state)

    result = VerificationAgent()(state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["total"] == 0
    assert result.data["verified"] == 0
    assert result.data["unverified"] == 0
    assert result.data["review_required"] == 0
    assert result.human_review_required is True


def test_verification_agent_rejects_invalid_evidence_id():
    state = make_state()

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": "not-a-valid-uuid"},
        ],
    )

    result = VerificationAgent()(state)

    assert result.status == AgentStatus.FAILED
    assert result.error.code == "INVALID_EVIDENCE_ID"


def test_verification_agent_verifies_matching_source_provenance(
    db_session,
    contract_api_data,
):
    evidence, clause = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="verified",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED

    assert result.data["total"] == 1
    assert result.data["verified"] == 1
    assert result.data["unverified"] == 0
    assert result.data["review_required"] == 0

    verification = result.data["results"][0]

    assert verification["outcome"] == "verified"
    assert verification["stored_verification_status"] == "verified"

    assert all(verification["checks"].values())

    assert result.data["legal_conclusions_established"] is False
    assert result.data["semantic_claim_verification_performed"] is False

    assert result.human_review_required is False
    assert sessions[0].was_closed is True


def test_verification_agent_distinguishes_unverified_evidence(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="unverified",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["unverified"] == 1
    assert result.data["verified"] == 0
    assert result.data["review_required"] == 0

    verification = result.data["results"][0]

    assert verification["outcome"] == "unverified"
    assert verification["checks"]["source_text_matches"] is True

    assert result.human_review_required is True
    assert result.unresolved_questions

    assert sessions[0].was_closed is True


def test_verification_agent_does_not_accept_rejected_evidence(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="rejected",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        excluded_obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["review_required"] == 1
    assert result.data["verified"] == 0

    verification = result.data["results"][0]

    assert verification["outcome"] == "review_required"
    assert verification["stored_verification_status"] == "rejected"

    assert any(
        "rejected" in issue.lower()
        for issue in verification["issues"]
    )

    assert result.human_review_required is True
    assert sessions[0].was_closed is True


def test_verification_agent_detects_source_text_mismatch(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="verified",
        evidence_text="The customer must provide 60 days notice.",
    )

    # Keep the stored offsets valid, but make the evidence excerpt
    # different from the actual clause source.
    evidence.evidence_text = "The customer must provide 90 days notice."
    db_session.flush()

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["review_required"] == 1

    verification = result.data["results"][0]

    assert verification["checks"]["document_matches"] is True
    assert verification["checks"]["page_matches"] is True
    assert verification["checks"]["offsets_valid"] is True
    assert verification["checks"]["source_text_matches"] is False

    assert verification["outcome"] == "review_required"
    assert result.human_review_required is True

    assert sessions[0].was_closed is True


def test_verification_agent_rejects_cross_organization_evidence(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_b"],
        verification_status="verified",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["review_required"] == 1
    assert result.data["verified"] == 0

    verification = result.data["results"][0]

    assert verification["outcome"] == "review_required"
    assert any(
        "organization" in issue.lower()
        for issue in verification["issues"]
    )

    assert result.human_review_required is True
    assert sessions[0].was_closed is True


def test_verification_agent_keeps_missing_evidence_unresolved(
    db_session,
    contract_api_data,
):
    missing_id = uuid4()

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(missing_id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["review_required"] == 1
    assert result.data["verified"] == 0

    verification = result.data["results"][0]

    assert verification["outcome"] == "review_required"
    assert result.human_review_required is True

    assert sessions[0].was_closed is True


def test_verification_agent_checks_excluded_evidence_too(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="rejected",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[],
        excluded_obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["total"] == 1
    assert result.data["review_required"] == 1

    assert sessions[0].was_closed is True


def test_verification_agent_does_not_mutate_database(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="unverified",
    )

    original_status = evidence.verification_status

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    def count_rows(model):
        return db_session.query(func.count(model.id)).scalar()

    before = {
        "clauses": count_rows(ContractClause),
        "evidence": count_rows(EvidenceRecord),
        "documents": count_rows(ContractDocument),
    }

    result, sessions = run_agent(db_session, state)

    after = {
        "clauses": count_rows(ContractClause),
        "evidence": count_rows(EvidenceRecord),
        "documents": count_rows(ContractDocument),
    }

    db_session.refresh(evidence)

    assert result.status == AgentStatus.COMPLETED
    assert after == before

    # Verification must never change the original human approval state.
    assert evidence.verification_status == original_status

    assert sessions[0].was_closed is True


def test_verification_agent_collects_evidence_references(
    db_session,
    contract_api_data,
):
    evidence, clause = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="verified",
    )

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": str(evidence.id)},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert len(result.evidence_references) == 1

    reference = result.evidence_references[0]

    assert reference.evidence_id == str(evidence.id)
    assert reference.document_id == str(
        contract_api_data["document_a"].id
    )
    assert reference.contract_id == str(
        contract_api_data["contract_a"].id
    )
    assert reference.clause_id == str(clause.id)

    assert reference.page_number == 1
    assert reference.char_start == clause.char_start
    assert reference.char_end == clause.char_end

    assert reference.excerpt == evidence.evidence_text
    assert reference.verification_status == "verified"

    assert sessions[0].was_closed is True


def test_verification_agent_deduplicates_evidence_ids(
    db_session,
    contract_api_data,
):
    evidence, _ = create_evidence(
        db_session,
        contract_api_data["document_a"],
        verification_status="verified",
    )

    evidence_id = str(evidence.id)

    state = make_state(
        contract_api_data["organization_a"].id,
    )

    add_obligation_result(
        state,
        obligations=[
            {"evidence_id": evidence_id},
        ],
        excluded_obligations=[
            {"evidence_id": evidence_id},
        ],
    )

    result, sessions = run_agent(db_session, state)

    assert result.status == AgentStatus.COMPLETED
    assert result.data["total"] == 1
    assert result.data["verified"] == 1

    assert sessions[0].was_closed is True