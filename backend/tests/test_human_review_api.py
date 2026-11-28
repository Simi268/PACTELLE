import uuid

from app.core.security import create_access_token
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.models.membership import OrganizationMembership
from app.models.user import User


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _create_evidence(db, document, prefix="review"):
    clause = ContractClause(
        document_id=document.id,
        clause_number=f"{prefix}-{uuid.uuid4().hex[:8]}",
        clause_title="Termination notice",
        category="termination",
        source_text="Either party must provide thirty days written notice.",
        page_number=2,
        char_start=10,
        char_end=66,
    )
    db.add(clause)
    db.flush()
    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Thirty days termination notice",
        evidence_type="termination_notice",
        evidence_text="Either party must provide thirty days written notice.",
        page_number=2,
        char_start=10,
        char_end=66,
        verification_status="unverified",
    )
    db.add(evidence)
    db.commit()
    return evidence


def _reviews_url(org_id):
    return f"/api/v1/organizations/{org_id}/reviews"


def test_member_can_create_evidence_backed_review_and_owner_can_approve(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    evidence = _create_evidence(db_session, data["document_a"])
    org_id = data["organization_a"].id

    created = api_client.post(
        _reviews_url(org_id),
        headers=_headers(data["member_a"]),
        json={
            "review_type": "interpretation",
            "reason": "Please confirm how the termination notice should be interpreted.",
            "evidence_record_ids": [str(evidence.id)],
            "execution_id": str(uuid.uuid4()),
            "proposed_interpretation": "Thirty calendar days of prior notice may be required.",
            "assigned_to_user_id": str(data["owner_a"].id),
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["evidence_snapshot"][0]["evidence_record_id"] == str(evidence.id)
    assert body["evidence_snapshot"][0]["verification_status_at_request"] == "unverified"
    assert len(body["audit_entries"]) == 1

    approved = api_client.post(
        f"{_reviews_url(org_id)}/{body['id']}/decision",
        headers=_headers(data["owner_a"]),
        json={"decision": "approved", "comment": "Reviewed; interpretation approved for this workflow."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by_user_id"] == str(data["owner_a"].id)
    assert [entry["event_type"] for entry in approved.json()["audit_entries"]] == ["created", "approved"]


def test_member_cannot_decide_review_request(api_client, db_session, contract_api_data):
    data = contract_api_data
    evidence = _create_evidence(db_session, data["document_a"], "memberdecision")
    created = api_client.post(
        _reviews_url(data["organization_a"].id),
        headers=_headers(data["member_a"]),
        json={
            "review_type": "legal_review",
            "reason": "Legal review is required for this clause.",
            "evidence_record_ids": [str(evidence.id)],
        },
    )
    review_id = created.json()["id"]
    response = api_client.post(
        f"{_reviews_url(data['organization_a'].id)}/{review_id}/decision",
        headers=_headers(data["member_a"]),
        json={"decision": "approved", "comment": "I approve this."},
    )
    assert response.status_code == 403


def test_review_cannot_reference_evidence_from_another_organization(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    evidence_b = _create_evidence(db_session, data["document_b"], "crossorg")
    response = api_client.post(
        _reviews_url(data["organization_a"].id),
        headers=_headers(data["owner_a"]),
        json={
            "review_type": "evidence_verification",
            "reason": "Check this evidence reference against the source.",
            "evidence_record_ids": [str(evidence_b.id)],
        },
    )
    assert response.status_code == 422


def test_assigned_reviewer_is_enforced(api_client, db_session, contract_api_data):
    data = contract_api_data
    evidence = _create_evidence(db_session, data["document_a"], "assigned")
    created = api_client.post(
        _reviews_url(data["organization_a"].id),
        headers=_headers(data["member_a"]),
        json={
            "review_type": "action_approval",
            "reason": "Please approve this proposed contractual action.",
            "evidence_record_ids": [str(evidence.id)],
            "assigned_to_user_id": str(data["owner_a"].id),
        },
    )
    review_id = created.json()["id"]
    other_admin = User(
        full_name="Other Admin",
        email=f"other-admin-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="test_hash",
        is_active=True,
    )
    db_session.add(other_admin)
    db_session.flush()
    db_session.add(OrganizationMembership(
        organization_id=data["organization_a"].id,
        user_id=other_admin.id,
        role="admin",
    ))
    db_session.commit()
    wrong_reviewer = api_client.post(
        f"{_reviews_url(data['organization_a'].id)}/{review_id}/decision",
        headers=_headers(other_admin),
        json={"decision": "rejected", "comment": "Not my assigned review."},
    )
    assert wrong_reviewer.status_code == 403


def test_nonexistent_evidence_is_rejected(api_client, contract_api_data):
    data = contract_api_data
    response = api_client.post(
        _reviews_url(data["organization_a"].id),
        headers=_headers(data["owner_a"]),
        json={
            "review_type": "interpretation",
            "reason": "Review this missing source reference.",
            "evidence_record_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 422
