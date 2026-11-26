
import uuid

import pytest

from sqlalchemy import select

from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.portfolio_risk_finding import (
    PortfolioRiskFinding,
    PortfolioRiskFindingContract,
    PortfolioRiskFindingEvidence,
)

from app.services.portfolio_finding_service import (
    persist_portfolio_findings,
    update_portfolio_finding_status,
    PortfolioFindingValidationError,
    PortfolioFindingNotFoundError,
)


def create_evidence(db, document, index=1):
    clause = ContractClause(
        document_id=document.id,
        clause_number=f"TEST-{index}",
        clause_title=f"Test Clause {index}",
        category="data_protection",
        source_text="Vendor must notify customer before changing subprocessors.",
        page_number=1,
        char_start=0,
        char_end=70,
    )

    db.add(clause)
    db.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Vendor must notify customer before changing subprocessors.",
        evidence_type="subprocessor_change_notice",
        evidence_text="Vendor must notify customer before changing subprocessors.",
        verification_status="verified",
    )

    db.add(evidence)
    db.flush()

    return evidence


def make_candidate(contract_ids, evidence_ids, rule_id=None):
    return {
        "finding_type": "potential_conflict",
        "title": "Potential operational dependency",
        "description": "Different responsibilities around subprocessor changes.",
        "severity": "medium",
        "status": "open",
        "assessment_status": "provisional",
        "detection_method": "rule_based",
        "rule_id": rule_id or f"test-rule-{uuid.uuid4()}",
        "rule_version": "1.0",
        "confidence": None,
        "details": {
            "legal_conflict_established": False,
            "requires_human_review": True,
        },
        "contract_ids": [str(item) for item in contract_ids],
        "evidence_ids": [str(item) for item in evidence_ids],
    }


def prepare_valid_data(db, contract_api_data):
    data = contract_api_data

    evidence_a = create_evidence(
        db,
        data["document_a"],
        1,
    )

    # Create a second document under Organization A's empty contract.
    second_document = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="second_contract.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/second_contract.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="processed",
    )

    db.add(second_document)
    db.flush()

    evidence_b = create_evidence(
        db,
        second_document,
        2,
    )

    candidate = make_candidate(
        [
            data["contract_a"].id,
            data["empty_contract"].id,
        ],
        [
            evidence_a.id,
            evidence_b.id,
        ],
    )

    return data, evidence_a, evidence_b, candidate


# --------------------------------------------------
# PERSISTENCE
# --------------------------------------------------


def test_persists_finding_with_contracts_and_evidence(
    db_session,
    contract_api_data,
):
    data, evidence_a, evidence_b, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    assert result["created_count"] == 1
    assert result["existing_count"] == 0

    finding = result["created_findings"][0]

    assert finding.organization_id == data["organization_a"].id
    assert finding.status == "open"
    assert finding.assessment_status == "provisional"

    contract_links = db_session.scalars(
        select(PortfolioRiskFindingContract).where(
            PortfolioRiskFindingContract.portfolio_finding_id
            == finding.id
        )
    ).all()

    evidence_links = db_session.scalars(
        select(PortfolioRiskFindingEvidence).where(
            PortfolioRiskFindingEvidence.portfolio_finding_id
            == finding.id
        )
    ).all()

    assert len(contract_links) == 2
    assert len(evidence_links) == 2


def test_duplicate_active_finding_is_reused(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    first = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    second = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["existing_count"] == 1

    findings = db_session.scalars(
        select(PortfolioRiskFinding).where(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id,
            PortfolioRiskFinding.rule_id == candidate["rule_id"],
        )
    ).all()

    assert len(findings) == 1


def test_resolved_finding_can_be_recreated(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    first = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    finding = first["created_findings"][0]

    update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "resolved",
    )

    second = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    assert second["created_count"] == 1


# --------------------------------------------------
# ORGANIZATION ISOLATION
# --------------------------------------------------


def test_rejects_contract_from_another_organization(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    evidence = create_evidence(
        db_session,
        data["document_a"],
    )

    candidate = make_candidate(
        [
            data["contract_a"].id,
            data["contract_b"].id,
        ],
        [evidence.id, evidence.id],
    )

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [candidate],
        )


def test_rejects_evidence_from_another_organization(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    evidence_a = create_evidence(
        db_session,
        data["document_a"],
    )

    evidence_b = create_evidence(
        db_session,
        data["document_b"],
    )

    candidate = make_candidate(
        [data["contract_a"].id],
        [evidence_a.id, evidence_b.id],
    )

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [candidate],
        )


def test_rejects_evidence_not_linked_to_finding_contracts(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    evidence_a = create_evidence(
        db_session,
        data["document_a"],
        1,
    )

    empty_document = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="extra.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/extra.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="processed",
    )

    db_session.add(empty_document)
    db_session.flush()

    unrelated_evidence = create_evidence(
        db_session,
        empty_document,
        2,
    )

    candidate = make_candidate(
        [
            data["contract_a"].id,
            data["contract_b"].id,
        ],
        [
            evidence_a.id,
            unrelated_evidence.id,
        ],
    )

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [candidate],
        )


# --------------------------------------------------
# VALIDATION
# --------------------------------------------------


def test_rejects_invalid_finding_type(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    candidate["finding_type"] = "invalid_type"

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [candidate],
        )


def test_rejects_invalid_severity(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    candidate["severity"] = "extreme"

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [candidate],
        )


def test_rejects_missing_organization(
    db_session,
    contract_api_data,
):
    _, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    with pytest.raises(PortfolioFindingNotFoundError):
        persist_portfolio_findings(
            db_session,
            uuid.uuid4(),
            [candidate],
        )


# --------------------------------------------------
# LIFECYCLE
# --------------------------------------------------


def test_finding_can_be_acknowledged_and_resolved(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    finding = result["created_findings"][0]

    acknowledged = update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "acknowledged",
    )

    assert acknowledged.status == "acknowledged"

    resolved = update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "resolved",
    )

    assert resolved.status == "resolved"


def test_resolved_finding_can_be_reopened(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    finding = result["created_findings"][0]

    update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "resolved",
    )

    reopened = update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "open",
    )

    assert reopened.status == "open"


def test_invalid_lifecycle_transition_is_rejected(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    finding = result["created_findings"][0]

    with pytest.raises(PortfolioFindingValidationError):
        update_portfolio_finding_status(
            db_session,
            data["organization_a"].id,
            finding.id,
            "open",
        )


def test_finding_cannot_be_updated_by_another_organization(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
    )

    finding = result["created_findings"][0]

    with pytest.raises(PortfolioFindingNotFoundError):
        update_portfolio_finding_status(
            db_session,
            data["organization_b"].id,
            finding.id,
            "acknowledged",
        )


# --------------------------------------------------
# TRANSACTION ROLLBACK
# --------------------------------------------------


def test_failed_batch_does_not_persist_partial_findings(
    db_session,
    contract_api_data,
):
    data, _, _, valid_candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    invalid_candidate = dict(valid_candidate)

    invalid_candidate["rule_id"] = f"invalid-{uuid.uuid4()}"
    invalid_candidate["severity"] = "invalid"

    with pytest.raises(PortfolioFindingValidationError):
        persist_portfolio_findings(
            db_session,
            data["organization_a"].id,
            [
                valid_candidate,
                invalid_candidate,
            ],
        )

    db_session.expire_all()

    persisted = db_session.scalars(
        select(PortfolioRiskFinding).where(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id,
            PortfolioRiskFinding.rule_id
            == valid_candidate["rule_id"],
        )
    ).all()

    assert persisted == []


def test_uncommitted_findings_can_be_rolled_back(
    db_session,
    contract_api_data,
):
    data, _, _, candidate = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    persist_portfolio_findings(
        db_session,
        data["organization_a"].id,
        [candidate],
        commit=False,
    )

    db_session.rollback()

    persisted = db_session.scalars(
        select(PortfolioRiskFinding).where(
            PortfolioRiskFinding.rule_id == candidate["rule_id"]
        )
    ).all()

    assert persisted == []
