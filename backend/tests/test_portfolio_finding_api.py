import uuid

from app.core.security import create_access_token
from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.services.portfolio_finding_service import (
    persist_portfolio_findings,
    update_portfolio_finding_status,
)


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def create_evidence(db, document, index=1):
    clause = ContractClause(
        document_id=document.id,
        clause_number=f"API-TEST-{index}-{uuid.uuid4().hex[:8]}",
        clause_title=f"API Test Clause {index}",
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


def prepare_finding_data(db, contract_api_data):
    data = contract_api_data

    evidence_a = create_evidence(db, data["document_a"], 1)

    second_document = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="portfolio_api_test.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/portfolio_api_test.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="processed",
    )
    db.add(second_document)
    db.flush()

    evidence_b = create_evidence(db, second_document, 2)

    return data, evidence_a, evidence_b


def create_portfolio_finding(
    db,
    organization_id,
    contract_api_data,
    *,
    rule_id=None,
    severity="medium",
    status="open",
):
    data, evidence_a, evidence_b = prepare_finding_data(
        db, contract_api_data
    )

    candidate = {
        "finding_type": "potential_conflict",
        "title": "Potential operational dependency",
        "description": "Different responsibilities around subprocessor changes.",
        "severity": severity,
        "status": status,
        "assessment_status": "provisional",
        "detection_method": "rule_based",
        "rule_id": rule_id or f"api-test-{uuid.uuid4()}",
        "rule_version": "1.0",
        "confidence": None,
        "details": {
            "legal_conflict_established": False,
            "requires_human_review": True,
        },
        "contract_ids": [
            str(data["contract_a"].id),
            str(data["empty_contract"].id),
        ],
        "evidence_ids": [
            str(evidence_a.id),
            str(evidence_b.id),
        ],
    }

    result = persist_portfolio_findings(
        db,
        organization_id,
        [candidate],
    )
    db.commit()

    finding = result["created_findings"][0]

    if status != "open":
        finding = update_portfolio_finding_status(
            db,
            organization_id,
            finding.id,
            status,
            commit=True,
        )

    return finding


def portfolio_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}/portfolio-findings"
    )


# --------------------------------------------------
# AUTHENTICATION AND AUTHORIZATION
# --------------------------------------------------


def test_portfolio_findings_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        portfolio_url(contract_api_data["organization_a"].id)
    )

    assert response.status_code == 401


def test_portfolio_findings_forbidden_for_non_member(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        portfolio_url(contract_api_data["organization_a"].id),
        headers=auth_headers(contract_api_data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_member_can_list_portfolio_findings(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
    )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["organization_id"] == str(data["organization_a"].id)
    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 20
    assert result["total_pages"] == 1
    assert len(result["findings"]) == 1

    finding = result["findings"][0]
    assert finding["finding_type"] == "potential_conflict"
    assert finding["severity"] == "medium"
    assert finding["status"] == "open"
    assert len(finding["contracts"]) == 2
    assert len(finding["evidence"]) == 2


# --------------------------------------------------
# DETAIL AND ORGANIZATION ISOLATION
# --------------------------------------------------


def test_member_can_retrieve_portfolio_finding_detail(
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

    response = api_client.get(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}",
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["id"] == str(finding.id)
    assert result["title"] == finding.title
    assert len(result["contracts"]) == 2
    assert len(result["evidence"]) == 2


def test_portfolio_findings_are_isolated_by_organization(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding_a = create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
    )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    findings = response.json()["findings"]

    assert len(findings) == 1
    assert findings[0]["id"] == str(finding_a.id)

    # Organization B must not be able to retrieve Organization A's finding.
    detail_response = api_client.get(
        f"{portfolio_url(data['organization_b'].id)}/{finding_a.id}",
        headers=auth_headers(data["outsider"]),
    )

    assert detail_response.status_code in (403, 404)


def test_finding_from_another_organization_returns_not_found(
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

    response = api_client.get(
        f"{portfolio_url(data['organization_b'].id)}/{finding.id}",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code in (403, 404)


# --------------------------------------------------
# FILTERING
# --------------------------------------------------


def test_portfolio_findings_filter_by_severity(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
        severity="high",
    )

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
        severity="low",
    )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        params={"severity": "high"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    result = response.json()

    assert result["total"] == 1
    assert result["findings"][0]["severity"] == "high"


def test_portfolio_findings_filter_by_status(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
        rule_id="api-status-open",
        status="open",
    )

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
        rule_id="api-status-acknowledged",
        status="acknowledged",
    )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        params={"status": "acknowledged"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    result = response.json()

    assert result["total"] == 1
    assert result["findings"][0]["status"] == "acknowledged"


def test_portfolio_findings_filter_by_type(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
    )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        params={"finding_type": "potential_conflict"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_portfolio_findings_reject_invalid_filters(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        portfolio_url(contract_api_data["organization_a"].id),
        params={"severity": "extreme"},
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 422


# --------------------------------------------------
# PAGINATION
# --------------------------------------------------


def test_portfolio_findings_pagination(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    for index in range(5):
        create_portfolio_finding(
            db_session,
            data["organization_a"].id,
            data,
            rule_id=f"api-pagination-{index}",
        )

    response = api_client.get(
        portfolio_url(data["organization_a"].id),
        params={"page": 1, "page_size": 2},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total"] == 5
    assert result["page"] == 1
    assert result["page_size"] == 2
    assert result["total_pages"] == 3
    assert len(result["findings"]) == 2


def test_portfolio_findings_reject_invalid_pagination(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        portfolio_url(contract_api_data["organization_a"].id),
        params={"page": 0, "page_size": 200},
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 422


# --------------------------------------------------
# HUMAN REVIEW AND STATUS LIFECYCLE
# --------------------------------------------------


def test_member_cannot_update_portfolio_finding_status(
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

    response = api_client.patch(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}/status",
        json={"status": "acknowledged"},
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 403


def test_owner_can_acknowledge_portfolio_finding(
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

    response = api_client.patch(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}/status",
        json={"status": "acknowledged"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"


def test_owner_can_resolve_portfolio_finding(
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

    response = api_client.patch(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}/status",
        json={"status": "resolved"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_invalid_portfolio_finding_status_transition_is_rejected(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding = create_portfolio_finding(
        db_session,
        data["organization_a"].id,
        data,
        status="open",
    )

    response = api_client.patch(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}/status",
        json={"status": "open"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 422


def test_invalid_status_value_is_rejected(
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

    response = api_client.patch(
        f"{portfolio_url(data['organization_a'].id)}/{finding.id}/status",
        json={"status": "pending"},
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 422

