
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from sqlalchemy import func

from app.models.organization import Organization
from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence

from app.services.risk_engine import detect_automatic_renewal_risk

from app.models.risk_event import RiskEvent

from app.services.risk_engine import (
    detect_automatic_renewal_risk,
    capture_risk_history_context,
)



def create_renewal_test_data(db_session):

    # 1. Create organization
    organization = Organization(
        name="Test Organization",
        industry="Technology"
    )

    db_session.add(organization)
    db_session.flush()

    # 2. Create contract
    contract = Contract(
        organization_id=organization.id,
        title="Test Vendor Agreement",
        contract_type="vendor",
        status="active",
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31)
    )

    db_session.add(contract)
    db_session.flush()

    # 3. Create document
    document = ContractDocument(
        contract_id=contract.id,
        original_filename="test_agreement.pdf",
        stored_filename="test_agreement_unique.pdf",
        storage_path="uploads/contracts/test_agreement_unique.pdf",
        file_type="application/pdf",
        file_size=1024,
        processing_status="extracted"
    )

    db_session.add(document)
    db_session.flush()

    # 4. Create clause
    clause = ContractClause(
        document_id=document.id,
        clause_number="3",
        clause_title="Term and Automatic Renewal",
        category="renewal",
        source_text=(
            "This agreement automatically renews for successive "
            "twelve (12) month periods. Either party must provide "
            "notice of non-renewal at least thirty (30) days "
            "before the end of the current term."
        ),
        page_number=1,
        char_start=0,
        char_end=200
    )

    db_session.add(clause)
    db_session.flush()

    # 5. Create renewal period evidence
    renewal_period = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="The agreement automatically renews for 12-month periods.",
        evidence_type="renewal_period",
        evidence_text=(
            "automatically renews for successive "
            "twelve (12) month periods"
        ),
        page_number=1,
        char_start=20,
        char_end=85
    )

    # 6. Create renewal notice evidence
    renewal_notice = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Non-renewal requires 30 days' advance notice.",
        evidence_type="renewal_notice",
        evidence_text=(
            "notice of non-renewal at least thirty (30) days "
            "before the end of the current term"
        ),
        page_number=1,
        char_start=100,
        char_end=190
    )

    db_session.add_all([renewal_period, renewal_notice])
    db_session.flush()

    return contract, renewal_period, renewal_notice


def test_detect_automatic_renewal_risk(db_session):

    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    # Verify risk creation
    assert result["status"] == "created"

    # Verify risk type
    assert result["risk_type"] == "renewal_exposure"

    # Verify notice period
    assert result["notice_period_days"] == 30

    # Verify deadline calculation
    assert result["deadline_date"] == "2026-12-01"

    # Verify supporting evidence count
    assert result["supporting_evidence_count"] == 2

    # Verify risk finding exists in database
    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    assert finding.deadline_date == date(2026, 12, 1)

    # Verify both evidence records are linked
    linked_count = db_session.query(
        func.count(RiskFindingEvidence.evidence_record_id)
    ).filter(
        RiskFindingEvidence.risk_finding_id == finding.id
    ).scalar()

    assert linked_count == 2


def test_duplicate_renewal_risk_is_not_created(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    first_result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert first_result["status"] == "created"

    second_result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert second_result["status"] == "already_exists"

    findings = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id,
        RiskFinding.rule_id == "RENEWAL-001",
        RiskFinding.status != "resolved"
    ).all()

    assert len(findings) == 1

    assert (
        first_result["risk_finding_id"]
        == second_result["risk_finding_id"]
    )

def test_missing_expiration_date_skips_detection(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    contract.expiration_date = None
    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "Contract expiration date is missing."

    findings = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).all()

    assert len(findings) == 0

def test_missing_renewal_evidence_skips_detection(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    # Remove all renewal evidence records
    db_session.query(EvidenceRecord).filter(
        EvidenceRecord.document_id.in_(
            db_session.query(ContractDocument.id).filter(
                ContractDocument.contract_id == contract.id
            )
        )
    ).delete(synchronize_session=False)

    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "skipped"

    assert result["reason"] == (
    "Required renewal evidence is incomplete."
)

    findings = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).all()

    assert len(findings) == 0


def test_existing_risk_deadline_is_backfilled(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    existing_finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description="Existing renewal risk.",
        severity="medium",
        status="open",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0",
        confidence=None,
        deadline_date=None
    )

    db_session.add(existing_finding)
    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "already_exists"
    assert result["deadline_date"] == "2026-12-01"

    db_session.refresh(existing_finding)

    assert existing_finding.deadline_date == date(2026, 12, 1)

    findings = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id,
        RiskFinding.rule_id == "RENEWAL-001",
        RiskFinding.status != "resolved"
    ).all()

    assert len(findings) == 1


def test_database_rejects_duplicate_active_risk(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    first_finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description="First renewal risk.",
        severity="medium",
        status="open",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0"
    )

    db_session.add(first_finding)
    db_session.commit()

    duplicate_finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Duplicate Renewal Exposure",
        description="This should be rejected.",
        severity="medium",
        status="open",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0"
    )

    db_session.add(duplicate_finding)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()

    existing_finding = db_session.query(RiskFinding).filter(
        RiskFinding.id == first_finding.id
    ).one()

    assert existing_finding.status == "open"

    existing_finding.status = "resolved"
    db_session.commit()

    new_finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Renewal Exposure - New Detection",
        description="New risk after previous resolution.",
        severity="medium",
        status="open",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0"
    )

    db_session.add(new_finding)
    db_session.commit()

    assert new_finding.id is not None
    assert new_finding.status == "open"

def test_unverified_evidence_creates_provisional_risk(db_session):

    contract, _, _ = create_renewal_test_data(db_session)

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "created"
    assert result["assessment_status"] == "provisional"

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    assert finding.assessment_status == "provisional"

def test_verified_evidence_creates_confirmed_risk(db_session):

    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    renewal_period.verification_status = "verified"
    renewal_notice.verification_status = "verified"

    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "created"
    assert result["assessment_status"] == "confirmed"

def test_rejected_evidence_is_not_used(db_session):

    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    renewal_period.verification_status = "rejected"

    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert result["status"] == "skipped"
    assert result["reason"] == (
        "Required renewal evidence is incomplete."
    )

    findings = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).all()

    assert len(findings) == 0

def test_provisional_risk_upgrades_after_evidence_verification(db_session):

    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    first_result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert first_result["assessment_status"] == "provisional"

    renewal_period.verification_status = "verified"
    renewal_notice.verification_status = "verified"

    db_session.flush()

    second_result = detect_automatic_renewal_risk(
        db_session,
        contract.id
    )

    assert second_result["status"] == "already_exists"
    assert second_result["assessment_status"] == "confirmed"

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    assert finding.assessment_status == "confirmed"

def test_rejected_evidence_downgrades_existing_confirmed_risk(
    db_session,
):
    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    renewal_period.verification_status = "verified"
    renewal_notice.verification_status = "verified"

    db_session.flush()

    first_result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    assert first_result["assessment_status"] == "confirmed"

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    assert finding.assessment_status == "confirmed"

    renewal_period.verification_status = "rejected"
    db_session.flush()

    second_result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    db_session.refresh(finding)

    assert second_result["status"] == "reconciled"
    assert finding.assessment_status == "provisional"
    assert finding.status == "open"

    linked_count = db_session.query(
        func.count(RiskFindingEvidence.evidence_record_id)
    ).filter(
        RiskFindingEvidence.risk_finding_id == finding.id
    ).scalar()

    assert linked_count == 0

def test_missing_evidence_downgrades_existing_finding(
    db_session,
):
    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    first_result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    assert first_result["assessment_status"] == "provisional"

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    db_session.delete(renewal_notice)
    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    db_session.refresh(finding)

    assert result["status"] == "reconciled"
    assert finding.assessment_status == "provisional"
    assert finding.status == "open"

    linked_count = db_session.query(
        func.count(RiskFindingEvidence.evidence_record_id)
    ).filter(
        RiskFindingEvidence.risk_finding_id == finding.id
    ).scalar()

    assert linked_count == 0

def test_replacing_supporting_evidence_removes_stale_links(
    db_session,
):
    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    first_result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    original_evidence_id = renewal_period.id

    replacement_evidence = EvidenceRecord(
        document_id=renewal_period.document_id,
        clause_id=renewal_period.clause_id,
        claim="The agreement automatically renews for 12-month periods.",
        evidence_type="renewal_period",
        evidence_text=(
            "automatically renews for successive "
            "twelve (12) month periods"
        ),
        page_number=1,
        char_start=25,
        char_end=90,
        verification_status="verified",
    )

    db_session.add(replacement_evidence)

    renewal_period.verification_status = "rejected"

    db_session.flush()

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    assert result["status"] == "already_exists"
    assert result["assessment_status"] == "provisional"

    linked_ids = {
        row[0]
        for row in db_session.query(
            RiskFindingEvidence.evidence_record_id
        ).filter(
            RiskFindingEvidence.risk_finding_id == finding.id
        ).all()
    }

    assert original_evidence_id not in linked_ids
    assert replacement_evidence.id in linked_ids
    assert renewal_notice.id in linked_ids
    assert len(linked_ids) == 2

def test_new_risk_persists_creation_event(db_session):
    contract, _, _ = create_renewal_test_data(db_session)

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
    )

    assert result["status"] == "created"

    events = (
        db_session.query(RiskEvent)
        .filter(
            RiskEvent.contract_id == contract.id,
            RiskEvent.event_type == "risk_created",
        )
        .all()
    )

    assert len(events) == 1
    assert events[0].risk_finding_id is not None
    assert events[0].source == "system"
    assert events[0].new_state["risk_type"] == "renewal_exposure"
    assert len(events[0].evidence_snapshot) == 2


def test_verification_upgrade_persists_assessment_event(db_session):
    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    detect_automatic_renewal_risk(db_session, contract.id)

    renewal_period.verification_status = "verified"
    renewal_notice.verification_status = "verified"
    db_session.flush()

    detect_automatic_renewal_risk(db_session, contract.id)

    events = (
        db_session.query(RiskEvent)
        .filter(
            RiskEvent.contract_id == contract.id,
            RiskEvent.event_type == "assessment_changed",
        )
        .all()
    )

    assert len(events) == 1
    assert events[0].previous_state["assessment_status"] == "provisional"
    assert events[0].new_state["assessment_status"] == "confirmed"


def test_changed_supporting_evidence_persists_evidence_event(db_session):
    contract, _, renewal_notice = create_renewal_test_data(db_session)

    detect_automatic_renewal_risk(db_session, contract.id)

    previous_state, previous_evidence = capture_risk_history_context(
        db_session,
        contract.id,
    )

    renewal_notice.evidence_text = (
        "notice of non-renewal at least thirty (30) days "
        "before the end of the current term, as specified"
    )
    db_session.flush()

    detect_automatic_renewal_risk(
        db_session,
        contract.id,
        previous_state=previous_state,
        previous_evidence=previous_evidence,
    )

    events = (
        db_session.query(RiskEvent)
        .filter(
            RiskEvent.contract_id == contract.id,
            RiskEvent.event_type == "evidence_changed",
        )
        .all()
    )

    assert len(events) == 1
    assert events[0].previous_state is not None
    assert events[0].evidence_snapshot is not None


def test_missing_evidence_persists_assessment_downgrade(db_session):
    contract, renewal_period, renewal_notice = (
        create_renewal_test_data(db_session)
    )

    renewal_period.verification_status = "verified"
    renewal_notice.verification_status = "verified"

    detect_automatic_renewal_risk(db_session, contract.id)

    renewal_period.verification_status = "rejected"
    db_session.flush()

    result = detect_automatic_renewal_risk(db_session, contract.id)

    assert result["status"] == "reconciled"

    events = (
        db_session.query(RiskEvent)
        .filter(
            RiskEvent.contract_id == contract.id,
            RiskEvent.event_type == "assessment_changed",
        )
        .all()
    )

    assert len(events) == 1
    assert events[0].previous_state["assessment_status"] == "confirmed"
    assert events[0].new_state["assessment_status"] == "provisional"

    finding = db_session.query(RiskFinding).filter(
        RiskFinding.contract_id == contract.id
    ).one()

    assert finding.status == "open"
    assert finding.assessment_status == "provisional"


def test_risk_events_rollback_with_risk_transaction(db_session):
    contract, _, _ = create_renewal_test_data(db_session)

    result = detect_automatic_renewal_risk(
        db_session,
        contract.id,
        commit=False,
    )

    assert result["status"] == "created"

    # Flush pending writes without committing the transaction.
    db_session.flush()
    # The event exists inside the current transaction.
    events_before_rollback = (
    db_session.query(RiskEvent)
    .filter(RiskEvent.contract_id == contract.id)
    .all()
)

    # The event exists inside the current transaction.
    events_before_rollback = (
        db_session.query(RiskEvent)
        .filter(RiskEvent.contract_id == contract.id)
        .all()
    )

    assert len(events_before_rollback) == 1

    # Roll back the risk and its event together.
    db_session.rollback()

    events_after_rollback = (
        db_session.query(RiskEvent)
        .filter(RiskEvent.contract_id == contract.id)
        .all()
    )

    findings_after_rollback = (
        db_session.query(RiskFinding)
        .filter(RiskFinding.contract_id == contract.id)
        .all()
    )

    assert events_after_rollback == []
    assert findings_after_rollback == []
