import uuid

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord

from app.services.portfolio_obligation_service import (
    retrieve_organization_obligations,
)


def create_document(db_session, contract, filename="test.pdf"):
    document = ContractDocument(
        contract_id=contract.id,
        original_filename=filename,
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/contracts/test.pdf",
        file_type="application/pdf",
        file_size=1024,
        processing_status="extracted",
    )

    db_session.add(document)
    db_session.flush()

    return document


def create_clause(db_session, document, clause_number="1"):
    clause = ContractClause(
        document_id=document.id,
        clause_number=clause_number,
        clause_title="Contractual Obligation",
        category="renewal",
        source_text=(
            "The customer must provide at least "
            "90 days' advance written notice."
        ),
        page_number=1,
        char_start=0,
        char_end=75,
        extraction_method="rule_based",
    )

    db_session.add(clause)
    db_session.flush()

    return clause


def create_evidence(
    db_session,
    document,
    clause,
    evidence_type="renewal_notice",
    claim="Non-renewal requires at least 90 days' advance written notice.",
    evidence_text="The customer must provide 90 days' advance written notice.",
    verification_status="unverified",
    confidence=None,
):
    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim=claim,
        evidence_type=evidence_type,
        evidence_text=evidence_text,
        page_number=1,
        char_start=0,
        char_end=len(evidence_text),
        extraction_method="rule_based",
        confidence=confidence,
        verification_status=verification_status,
    )

    db_session.add(evidence)
    db_session.flush()

    return evidence


# --------------------------------------------------
# MULTI-CONTRACT RETRIEVAL
# --------------------------------------------------


def test_retrieves_obligations_across_multiple_contracts(
    db_session,
    contract_api_data,
):
    contract_a = contract_api_data["contract_a"]
    contract_b = contract_api_data["empty_contract"]

    document_a = contract_api_data["document_a"]

    document_b = create_document(
        db_session,
        contract_b,
        "agreement_b.pdf",
    )

    clause_a = create_clause(
        db_session,
        document_a,
        "1",
    )

    clause_b = create_clause(
        db_session,
        document_b,
        "2",
    )

    create_evidence(
        db_session,
        document_a,
        clause_a,
    )

    create_evidence(
        db_session,
        document_b,
        clause_b,
        claim="Non-renewal requires at least 60 days' notice.",
        evidence_text="The customer must provide 60 days' notice.",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert result["summary"]["normalized_obligations"] == 2

    assert result["summary"]["contracts_with_obligations"] == 2

    assert len(result["obligations"]) == 2

    retrieved_contract_ids = {
        item["contract_id"]
        for item in result["obligations"]
    }

    assert retrieved_contract_ids == {
        str(contract_a.id),
        str(contract_b.id),
    }


# --------------------------------------------------
# ORGANIZATION ISOLATION
# --------------------------------------------------


def test_retrieval_isolated_by_organization(
    db_session,
    contract_api_data,
):
    document_a = contract_api_data["document_a"]
    document_b = contract_api_data["document_b"]

    clause_a = create_clause(
        db_session,
        document_a,
    )

    clause_b = create_clause(
        db_session,
        document_b,
    )

    create_evidence(
        db_session,
        document_a,
        clause_a,
    )

    create_evidence(
        db_session,
        document_b,
        clause_b,
        claim="Non-renewal requires at least 30 days' notice.",
        evidence_text="The customer must provide 30 days' notice.",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert result["summary"]["normalized_obligations"] == 1

    assert all(
        item["contract_id"]
        == str(contract_api_data["contract_a"].id)
        for item in result["obligations"]
    )

    assert all(
        item["contract_id"]
        != str(contract_api_data["contract_b"].id)
        for item in result["obligations"]
    )


# --------------------------------------------------
# REJECTED EVIDENCE
# --------------------------------------------------


def test_rejected_evidence_excluded_from_analysis(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    clause = create_clause(
        db_session,
        document,
    )

    create_evidence(
        db_session,
        document,
        clause,
        verification_status="rejected",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert result["summary"]["normalized_obligations"] == 0

    assert result["summary"]["excluded_rejected_evidence"] == 1

    assert len(result["obligations"]) == 0

    assert len(result["excluded_obligations"]) == 1

    assert (
        result["excluded_obligations"][0]["verification_status"]
        == "rejected"
    )

    assert (
        result["excluded_obligations"][0]["analysis_eligible"]
        is False
    )


# --------------------------------------------------
# UNVERIFIED EVIDENCE
# --------------------------------------------------


def test_unverified_evidence_remains_eligible_for_preliminary_analysis(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    clause = create_clause(
        db_session,
        document,
    )

    create_evidence(
        db_session,
        document,
        clause,
        verification_status="unverified",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert result["summary"]["normalized_obligations"] == 1

    obligation = result["obligations"][0]

    assert obligation["verification_status"] == "unverified"

    assert obligation["analysis_eligible"] is True


# --------------------------------------------------
# UNSUPPORTED EVIDENCE
# --------------------------------------------------


def test_unsupported_evidence_types_are_ignored(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    clause = create_clause(
        db_session,
        document,
    )

    create_evidence(
        db_session,
        document,
        clause,
        evidence_type="unsupported_obligation",
        claim="Some unsupported contractual claim.",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert result["summary"]["total_evidence_records"] == 1

    assert result["summary"]["normalized_obligations"] == 0

    assert result["summary"]["unsupported_evidence"] == 1

    assert result["obligations"] == []


# --------------------------------------------------
# EMPTY ORGANIZATION
# --------------------------------------------------


def test_empty_organization_returns_empty_result(
    db_session,
    contract_api_data,
):
    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_b"].id,
    )

    assert result["summary"]["total_evidence_records"] == 0

    assert result["summary"]["normalized_obligations"] == 0

    assert result["summary"]["excluded_rejected_evidence"] == 0

    assert result["summary"]["unsupported_evidence"] == 0

    assert result["summary"]["contracts_with_obligations"] == 0

    assert result["obligations"] == []

    assert result["excluded_obligations"] == []


# --------------------------------------------------
# GROUPING
# --------------------------------------------------


def test_obligations_grouped_by_family_and_type(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    clause = create_clause(
        db_session,
        document,
    )

    create_evidence(
        db_session,
        document,
        clause,
        evidence_type="renewal_notice",
        claim="Non-renewal requires 90 days' notice.",
    )

    create_evidence(
        db_session,
        document,
        clause,
        evidence_type="renewal_period",
        claim="The agreement automatically renews for successive 12-month periods.",
    )

    create_evidence(
        db_session,
        document,
        clause,
        evidence_type="payment_deadline",
        claim="Payment is due within 30 days.",
    )

    db_session.flush()

    result = retrieve_organization_obligations(
        db_session,
        contract_api_data["organization_a"].id,
    )

    assert len(result["obligations"]) == 3

    assert len(result["grouped_by_family"]["renewal"]) == 2

    assert len(result["grouped_by_family"]["payment"]) == 1

    assert len(result["grouped_by_type"]["renewal_notice"]) == 1

    assert len(result["grouped_by_type"]["renewal_period"]) == 1

    assert len(result["grouped_by_type"]["payment_deadline"]) == 1