import uuid

from app.core.security import create_access_token
from app.models.membership import OrganizationMembership
from app.models.portfolio_risk_finding import PortfolioRiskFinding

from tests.test_portfolio_finding_api import (
    auth_headers,
    create_portfolio_finding,
    portfolio_url,
)
import uuid

from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord

def analysis_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/portfolio-analysis"
    )


# --------------------------------------------------
# AUTHENTICATION AND AUTHORIZATION
# --------------------------------------------------

def test_portfolio_analysis_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.post(
        analysis_url(contract_api_data["organization_a"].id)
    )

    assert response.status_code == 401


def test_member_cannot_trigger_portfolio_analysis(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 403


def test_outsider_cannot_trigger_portfolio_analysis(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_owner_can_trigger_portfolio_analysis(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200


def test_organization_b_owner_cannot_analyze_organization_a(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["owner_b"]),
    )

    assert response.status_code in (403, 404)


# --------------------------------------------------
# ANALYSIS RESPONSE
# --------------------------------------------------

def test_analysis_returns_expected_response_structure(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["organization_id"] == str(
        data["organization_a"].id
    )

    assert result["status"] == "completed"

    assert "summary" in result
    assert "retrieval" in result["summary"]
    assert "intelligence" in result["summary"]
    assert "generation" in result["summary"]
    assert "persistence" in result["summary"]

    assert "findings" in result
    assert "human_review_queue" in result

    assert isinstance(result["findings"], list)
    assert isinstance(result["human_review_queue"], list)


def test_analysis_retrieves_only_organization_obligations(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    response = api_client.post(
        analysis_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    # The initial test fixture has no evidence records.
    # Analysis must not accidentally include Organization B.
    assert result["summary"]["retrieval"][
        "contracts_with_obligations"
    ] == 0


# --------------------------------------------------
# FINDING PERSISTENCE AND HUMAN REVIEW
# --------------------------------------------------

def test_analysis_does_not_create_duplicate_findings(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    url = analysis_url(data["organization_a"].id)
    headers = auth_headers(data["owner_a"])

    first_response = api_client.post(
        url,
        headers=headers,
    )

    second_response = api_client.post(
        url,
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    findings = (
        db_session.query(PortfolioRiskFinding)
        .filter(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
        .all()
    )

    rule_ids = [finding.rule_id for finding in findings]

    assert len(rule_ids) == len(set(rule_ids))


def test_existing_findings_remain_provisional_until_review(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding = create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
    )

    assert finding.assessment_status == "provisional"
    assert finding.status == "open"

    response = api_client.get(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["assessment_status"] == "provisional"
    assert result["details"]["legal_conflict_established"] is False
    assert result["details"]["requires_human_review"] is True


def create_dependency_evidence(
    db,
    document,
    text,
    index,
):
    clause = ContractClause(
        document_id=document.id,
        clause_number=f"DEPENDENCY-{index}-{uuid.uuid4().hex[:8]}",
        clause_title="Subprocessor Change Obligation",
        category="data_protection",
        source_text=text,
        page_number=1,
        char_start=0,
        char_end=len(text),
    )

    db.add(clause)
    db.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim=text,
        evidence_type="subprocessor_change_notice",
        evidence_text=text,
        verification_status="verified",
        confidence=0.95,
    )

    db.add(evidence)
    db.flush()

    return evidence

def test_portfolio_analysis_generates_and_persists_real_finding(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    # First contract already has a document.
    document_a = data["document_a"]

    # Create a document for the second contract.
    document_b = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="agreement_b_dependency.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/agreement_b_dependency.pdf",
        file_type="application/pdf",
        file_size=1024,
        processing_status="processed",
    )

    db_session.add(document_b)
    db_session.flush()

    # Two verified obligations with:
    # - Same subprocessor-change trigger.
    # - Different responsible parties.
    # - Different notice/approval periods.

    evidence_a = create_dependency_evidence(
        db_session,
        document_a,
        (
            "Vendor shall notify Customer "
            "90 days before changing subprocessors."
        ),
        1,
    )

    evidence_b = create_dependency_evidence(
        db_session,
        document_b,
        (
            "Customer shall approve subprocessor changes "
            "30 days before implementation."
        ),
        2,
    )

    db_session.commit()

    url = analysis_url(data["organization_a"].id)
    headers = auth_headers(data["owner_a"])

    # First analysis.
    first_response = api_client.post(
        url,
        headers=headers,
    )

    assert first_response.status_code == 200

    first_result = first_response.json()

    assert first_result["summary"]["retrieval"][
        "contracts_with_obligations"
    ] == 2

    assert first_result["summary"]["generation"][
        "generated_findings"
    ] == 1

    assert first_result["summary"]["persistence"][
        "created_count"
    ] == 1

    assert len(first_result["findings"]) == 1

    finding = first_result["findings"][0]

    assert finding["finding_type"] == "potential_conflict"
    assert finding["assessment_status"] == "provisional"
    assert finding["status"] == "open"

    assert finding["details"][
        "legal_conflict_established"
    ] is False

    assert finding["details"][
        "requires_human_review"
    ] is True

    assert len(finding["contracts"]) == 2
    assert len(finding["evidence"]) == 2

    returned_evidence_ids = {
        item["evidence_id"]
        for item in finding["evidence"]
    }

    assert returned_evidence_ids == {
        str(evidence_a.id),
        str(evidence_b.id),
    }

    # Second analysis must reuse the existing active finding.
    second_response = api_client.post(
        url,
        headers=headers,
    )

    assert second_response.status_code == 200

    second_result = second_response.json()

    assert second_result["summary"]["generation"][
        "generated_findings"
    ] == 1

    assert second_result["summary"]["persistence"][
        "created_count"
    ] == 0

    assert second_result["summary"]["persistence"][
        "existing_count"
    ] == 1

    # Verify the database contains exactly one finding.
    findings = (
        db_session.query(PortfolioRiskFinding)
        .filter(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
        .all()
    )

    assert len(findings) == 1
    assert findings[0].assessment_status == "provisional"