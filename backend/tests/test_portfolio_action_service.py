import uuid

import pytest
from sqlalchemy import select

from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.services.portfolio_finding_service import persist_portfolio_findings
from app.services.portfolio_action_service import (
    PortfolioActionNotFoundError,
    PortfolioActionValidationError,
    create_portfolio_action,
    generate_actions_for_finding,
    get_portfolio_action,
    transition_portfolio_action,
)
from app.models.portfolio_risk_action import (
    PortfolioRiskAction,
    PortfolioRiskActionAudit,
)


def _create_finding(db, data, finding_type="potential_conflict", severity="high"):
    clause = ContractClause(
        document_id=data["document_a"].id,
        clause_number=f"ACTION-{uuid.uuid4().hex[:8]}",
        clause_title="Action test clause",
        category="data_protection",
        source_text="Vendor shall notify customer before changing subprocessors.",
        page_number=1,
        char_start=0,
        char_end=70,
    )
    db.add(clause)
    db.flush()
    evidence_a = EvidenceRecord(
        document_id=data["document_a"].id,
        clause_id=clause.id,
        claim="Vendor notice obligation",
        evidence_type="subprocessor_change_notice",
        evidence_text="Vendor shall notify customer before changing subprocessors.",
        verification_status="verified",
    )
    second_document = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="action_second.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/action_second.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="processed",
    )
    db.add(second_document)
    db.flush()
    second_clause = ContractClause(
        document_id=second_document.id,
        clause_number=f"ACTION-B-{uuid.uuid4().hex[:8]}",
        clause_title="Second action test clause",
        category="data_protection",
        source_text="Customer shall approve subprocessor changes.",
        page_number=1,
        char_start=0,
        char_end=50,
    )
    db.add(second_clause)
    db.flush()
    evidence_b = EvidenceRecord(
        document_id=second_document.id,
        clause_id=second_clause.id,
        claim="Customer approval obligation",
        evidence_type="subprocessor_change_approval",
        evidence_text="Customer shall approve subprocessor changes.",
        verification_status="verified",
    )
    db.add_all([evidence_a, evidence_b])
    db.flush()

    candidate = {
        "finding_type": finding_type,
        "title": "Action test finding",
        "description": "A finding used to test action workflows.",
        "severity": severity,
        "assessment_status": "provisional",
        "detection_method": "rule_based",
        "rule_id": f"action-test-{uuid.uuid4()}",
        "rule_version": "1.0",
        "confidence": None,
        "details": {"requires_human_review": True},
        "contract_ids": [str(data["contract_a"].id), str(data["empty_contract"].id)],
        "evidence_ids": [str(evidence_a.id), str(evidence_b.id)],
    }
    result = persist_portfolio_findings(db, data["organization_a"].id, [candidate])
    db.flush()
    return result["created_findings"][0]


def test_generates_recommendations_and_deduplicates(db_session, contract_api_data):
    data = contract_api_data
    finding = _create_finding(db_session, data)
    first = generate_actions_for_finding(
        db_session, data["organization_a"].id, finding.id, data["owner_a"].id
    )
    second = generate_actions_for_finding(
        db_session, data["organization_a"].id, finding.id, data["owner_a"].id
    )
    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert second["existing_count"] == 2
    assert all(item.status == "proposed" for item in first["created_actions"])


def test_action_lifecycle_writes_audit_history(db_session, contract_api_data):
    data = contract_api_data
    finding = _create_finding(db_session, data)
    action = create_portfolio_action(
        db_session,
        data["organization_a"].id,
        finding.id,
        data["owner_a"].id,
        title="Review clauses",
        description="Review both clauses.",
        rationale="Potential operational dependency.",
        priority="high",
    )
    transition_portfolio_action(
        db_session, data["organization_a"].id, action.id,
        data["owner_a"].id, "approved",
    )
    transition_portfolio_action(
        db_session, data["organization_a"].id, action.id,
        data["owner_a"].id, "in_progress",
    )
    transition_portfolio_action(
        db_session, data["organization_a"].id, action.id,
        data["owner_a"].id, "completed",
    )
    db_session.flush()
    refreshed = get_portfolio_action(db_session, data["organization_a"].id, action.id)
    assert refreshed.status == "completed"
    assert len(refreshed.audit_entries) == 4
    assert finding.status == "open"


def test_rejection_requires_reason(db_session, contract_api_data):
    data = contract_api_data
    finding = _create_finding(db_session, data)
    action = create_portfolio_action(
        db_session, data["organization_a"].id, finding.id, data["owner_a"].id,
        title="Review", description="Review.", rationale="Reason.", priority="medium",
    )
    with pytest.raises(PortfolioActionValidationError):
        transition_portfolio_action(
            db_session, data["organization_a"].id, action.id,
            data["owner_a"].id, "rejected",
        )


def test_cannot_assign_user_from_another_organization(db_session, contract_api_data):
    data = contract_api_data
    finding = _create_finding(db_session, data)
    with pytest.raises(PortfolioActionValidationError):
        create_portfolio_action(
            db_session, data["organization_a"].id, finding.id, data["owner_a"].id,
            title="Review", description="Review.", rationale="Reason.",
            priority="medium", assigned_to_user_id=data["owner_b"].id,
        )


def test_finding_is_organization_scoped(db_session, contract_api_data):
    data = contract_api_data
    finding = _create_finding(db_session, data)
    with pytest.raises(PortfolioActionNotFoundError):
        create_portfolio_action(
            db_session, data["organization_b"].id, finding.id, data["owner_b"].id,
            title="Review", description="Review.", rationale="Reason.",
            priority="medium",
        )
