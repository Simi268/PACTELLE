import uuid

from app.core.security import create_access_token
from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.services.portfolio_finding_service import persist_portfolio_findings


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _make_finding(db, data):
    clause_a = ContractClause(
        document_id=data["document_a"].id,
        clause_number=f"API-A-{uuid.uuid4().hex[:8]}",
        clause_title="Vendor notice",
        category="data_protection",
        source_text="Vendor shall notify customer before changing subprocessors.",
        page_number=1,
        char_start=0,
        char_end=60,
    )
    db.add(clause_a)
    db.flush()
    evidence_a = EvidenceRecord(
        document_id=data["document_a"].id,
        clause_id=clause_a.id,
        claim="Vendor notice",
        evidence_type="subprocessor_change_notice",
        evidence_text="Vendor shall notify customer before changing subprocessors.",
        verification_status="verified",
    )
    document_b = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="action_api_b.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/action_api_b.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="processed",
    )
    db.add(document_b)
    db.flush()
    clause_b = ContractClause(
        document_id=document_b.id,
        clause_number=f"API-B-{uuid.uuid4().hex[:8]}",
        clause_title="Customer approval",
        category="data_protection",
        source_text="Customer shall approve subprocessor changes.",
        page_number=1,
        char_start=0,
        char_end=50,
    )
    db.add(clause_b)
    db.flush()
    evidence_b = EvidenceRecord(
        document_id=document_b.id,
        clause_id=clause_b.id,
        claim="Customer approval",
        evidence_type="subprocessor_change_approval",
        evidence_text="Customer shall approve subprocessor changes.",
        verification_status="verified",
    )
    db.add_all([evidence_a, evidence_b])
    db.flush()
    result = persist_portfolio_findings(
        db,
        data["organization_a"].id,
        [{
            "finding_type": "potential_conflict",
            "title": "Potential operational dependency",
            "description": "Review related obligations.",
            "severity": "high",
            "assessment_status": "provisional",
            "detection_method": "rule_based",
            "rule_id": f"action-api-{uuid.uuid4()}",
            "rule_version": "1.0",
            "confidence": None,
            "details": {"requires_human_review": True},
            "contract_ids": [
                str(data["contract_a"].id),
                str(data["empty_contract"].id),
            ],
            "evidence_ids": [str(evidence_a.id), str(evidence_b.id)],
        }],
    )
    db.flush()
    return result["created_findings"][0]


def _base(organization_id):
    return f"/api/v1/organizations/{organization_id}/portfolio-actions"


def test_member_can_list_but_cannot_create_or_approve_actions(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    finding = _make_finding(db_session, data)
    db_session.commit()
    headers = _headers(data["member_a"])

    listing = api_client.get(_base(data["organization_a"].id), headers=headers)
    assert listing.status_code == 200

    create = api_client.post(
        _base(data["organization_a"].id),
        headers=headers,
        json={
            "finding_id": str(finding.id),
            "title": "Review clauses",
            "description": "Review linked clauses.",
            "rationale": "Potential dependency.",
            "priority": "high",
        },
    )
    assert create.status_code == 403


def test_owner_can_generate_recommendations_and_approve_action(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    finding = _make_finding(db_session, data)
    db_session.commit()
    headers = _headers(data["owner_a"])
    org_id = data["organization_a"].id

    generated = api_client.post(
        f"/api/v1/organizations/{org_id}/portfolio-findings/{finding.id}/action-recommendations",
        headers=headers,
    )
    assert generated.status_code == 200
    assert generated.json()["created_count"] == 2

    action_id = generated.json()["actions"][0]["id"]
    approved = api_client.patch(
        f"{_base(org_id)}/{action_id}/status",
        headers=headers,
        json={"status": "approved", "comment": "Reviewed and approved."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert len(approved.json()["audit_entries"]) >= 2


def test_recommendations_are_not_visible_across_organizations(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    finding = _make_finding(db_session, data)
    db_session.commit()
    response = api_client.post(
        f"/api/v1/organizations/{data['organization_b'].id}/portfolio-findings/{finding.id}/action-recommendations",
        headers=_headers(data["owner_b"]),
    )
    assert response.status_code == 404
