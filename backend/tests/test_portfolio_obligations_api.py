from datetime import date, timedelta
from uuid import uuid4

from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.models.contractual_obligation import ContractualObligation
from app.core.security import create_access_token


def create_api_obligation(db_session, data):
    document = data["document_a"]

    clause = ContractClause(
        document_id=document.id,
        clause_number=f"API-OBL-{uuid4().hex[:8]}",
        clause_title="Renewal Notice",
        category="renewal",
        source_text=(
            "The customer must provide at least "
            "30 days' advance written notice before renewal."
        ),
        page_number=1,
        char_start=0,
        char_end=100,
        extraction_method="rule_based",
    )

    db_session.add(clause)
    db_session.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Notice must be provided before renewal.",
        evidence_type="renewal_notice",
        evidence_text=(
            "The customer must provide at least "
            "30 days' advance written notice before renewal."
        ),
        page_number=1,
        char_start=0,
        char_end=100,
        extraction_method="rule_based",
        confidence=0.9,
        verification_status="verified",
        is_current=True,
    )

    db_session.add(evidence)
    db_session.flush()

    obligation = ContractualObligation(
        organization_id=data["organization_a"].id,
        contract_id=data["contract_a"].id,
        evidence_record_id=evidence.id,
        obligation_type="renewal_notice",
        obligation_family="renewal",
        description="Advance notice is required before renewal.",
        claim=evidence.claim,
        original_text=evidence.evidence_text,
        verification_status="verified",
        confidence=0.9,
        status="open",
        due_date=date.today() + timedelta(days=30),
    )

    db_session.add(obligation)
    db_session.flush()

    return obligation


def headers(user):
    return {
        "Authorization": f"Bearer {create_access_token(user.id)}"
    }


def test_member_can_list_organization_obligations(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_api_obligation(db_session, data)

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}/obligations",
        headers=headers(data["member_a"]),
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["total"] >= 1
    assert any(
        item["id"] == str(obligation.id)
        for item in payload["obligations"]
    )


def test_member_can_get_obligation_details(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_api_obligation(db_session, data)

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}/obligations/{obligation.id}",
        headers=headers(data["member_a"]),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(obligation.id)


def test_member_cannot_update_obligation(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_api_obligation(db_session, data)

    response = api_client.patch(
        f"/api/v1/organizations/{data['organization_a'].id}/obligations/{obligation.id}",
        headers=headers(data["member_a"]),
        json={"status": "in_progress"},
    )

    assert response.status_code == 403


def test_owner_can_update_obligation_due_date(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_api_obligation(db_session, data)

    due_date = (date.today() + timedelta(days=60)).isoformat()

    response = api_client.patch(
        f"/api/v1/organizations/{data['organization_a'].id}/obligations/{obligation.id}",
        headers=headers(data["owner_a"]),
        json={"due_date": due_date},
    )

    assert response.status_code == 200
    assert response.json()["due_date"] == due_date


def test_obligation_details_are_organization_scoped(
    api_client, db_session, contract_api_data
):
    data = contract_api_data
    obligation = create_api_obligation(db_session, data)

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_b'].id}/obligations/{obligation.id}",
        headers=headers(data["owner_b"]),
    )

    assert response.status_code == 404


def test_invalid_status_filter_returns_422(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}/obligations?status=invalid",
        headers=headers(data["owner_a"]),
    )

    assert response.status_code == 422