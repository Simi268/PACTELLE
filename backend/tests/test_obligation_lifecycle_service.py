from datetime import date, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select

from app.models.evidence_record import EvidenceRecord
from app.models.contractual_obligation import (
    ContractualObligation,
    ContractualObligationAudit,
)
from app.services.obligation_lifecycle_service import (
    ObligationNotFoundError,
    ObligationValidationError,
    get_organization_obligation,
    list_organization_obligations,
    update_organization_obligation,
)
from app.models.clause import ContractClause

def create_evidence(db_session, data):
    document = data["document_a"]

    clause = ContractClause(
        document_id=document.id,
        clause_number=f"TEST-{uuid4().hex[:8]}",
        clause_title="Renewal Notice",
        category="renewal",
        source_text="Written notice must be provided 30 days before renewal.",
        page_number=1,
        char_start=0,
        char_end=75,
        extraction_method="rule_based",
    )

    db_session.add(clause)
    db_session.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Written notice must be provided before renewal.",
        evidence_type="renewal_notice",
        evidence_text="Written notice must be provided 30 days before renewal.",
        page_number=1,
        char_start=0,
        char_end=75,
        extraction_method="rule_based",
        confidence=0.95,
        verification_status="verified",
        is_current=True,
    )

    db_session.add(evidence)
    db_session.flush()

    return evidence


def create_obligation(db_session, data):
    evidence = create_evidence(db_session, data)

    obligation = ContractualObligation(
        organization_id=data["organization_a"].id,
        contract_id=data["contract_a"].id,
        evidence_record_id=evidence.id,
        obligation_type="renewal_notice",
        obligation_family="renewal",
        description="Advance notice is required before renewal.",
        claim="Written notice must be provided before renewal.",
        original_text="Written notice must be provided 30 days before renewal.",
        duration={"value": 30, "unit": "days"},
        verification_status="verified",
        confidence=0.95,
        status="open",
    )

    db_session.add(obligation)
    db_session.flush()

    return obligation


def test_obligation_can_be_assigned_to_organization_member(
    db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        assigned_to_user_id=data["member_a"].id,
        assignment_supplied=True,
    )

    assert updated.assigned_to_user_id == data["member_a"].id


def test_obligation_rejects_assignment_to_non_member(
    db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    with pytest.raises(ObligationValidationError):
        update_organization_obligation(
            db_session,
            data["organization_a"].id,
            obligation.id,
            data["owner_a"].id,
            assigned_to_user_id=data["outsider"].id,
            assignment_supplied=True,
        )


def test_obligation_can_receive_due_date(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    due_date = date.today() + timedelta(days=30)

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        due_date=due_date,
        due_date_supplied=True,
    )

    assert updated.due_date == due_date


def test_due_date_can_be_cleared(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    obligation.due_date = date.today() + timedelta(days=30)
    db_session.flush()

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        due_date=None,
        due_date_supplied=True,
    )

    assert updated.due_date is None


def test_obligation_can_move_to_in_progress(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        status="in_progress",
    )

    assert updated.status == "in_progress"


def test_completion_requires_a_note(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    with pytest.raises(ObligationValidationError):
        update_organization_obligation(
            db_session,
            data["organization_a"].id,
            obligation.id,
            data["owner_a"].id,
            status="completed",
        )


def test_obligation_can_be_completed_with_note(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        status="completed",
        completion_note="The required action has been completed.",
    )

    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.completion_note


def test_waiver_requires_a_reason(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    with pytest.raises(ObligationValidationError):
        update_organization_obligation(
            db_session,
            data["organization_a"].id,
            obligation.id,
            data["owner_a"].id,
            status="waived",
        )


def test_obligation_can_be_waived(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    updated = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        status="waived",
        waived_reason="The obligation is no longer applicable.",
    )

    assert updated.status == "waived"
    assert updated.waived_reason


def test_invalid_status_transition_is_rejected(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    completed = update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        status="completed",
        completion_note="Completed.",
    )

    assert completed.status == "completed"

    with pytest.raises(ObligationValidationError):
        update_organization_obligation(
            db_session,
            data["organization_a"].id,
            obligation.id,
            data["owner_a"].id,
            status="in_progress",
        )


def test_obligation_creates_audit_entries(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    update_organization_obligation(
        db_session,
        data["organization_a"].id,
        obligation.id,
        data["owner_a"].id,
        status="in_progress",
    )

    audits = db_session.scalars(
        select(ContractualObligationAudit).where(
            ContractualObligationAudit.obligation_id == obligation.id
        )
    ).all()

    assert any(a.event_type == "status_changed" for a in audits)


def test_obligation_is_isolated_by_organization(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    with pytest.raises(ObligationNotFoundError):
        get_organization_obligation(
            db_session,
            data["organization_b"].id,
            obligation.id,
        )


def test_list_obligations_is_organization_scoped(db_session, contract_api_data):
    data = contract_api_data
    obligation = create_obligation(db_session, data)

    records, total = list_organization_obligations(
        db_session,
        data["organization_a"].id,
    )

    assert total >= 1
    assert any(item.id == obligation.id for item in records)

    other_records, _ = list_organization_obligations(
        db_session,
        data["organization_b"].id,
    )

    assert obligation.id not in [item.id for item in other_records]