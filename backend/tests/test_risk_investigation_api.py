from uuid import uuid4

from app.core.security import create_access_token
from app.models.risk_finding import RiskFinding
from app.models.risk_event import RiskEvent


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def create_finding(db_session, contract):
    finding = RiskFinding(
        contract_id=contract.id,
        risk_type="automatic_renewal",
        title="Automatic Renewal Risk",
        description="Contract may renew automatically.",
        severity="high",
        status="open",
        assessment_status="confirmed",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0",
        confidence=0.95,
    )

    db_session.add(finding)
    db_session.flush()

    return finding


def create_event(db_session, contract, finding):
    event = RiskEvent(
        contract_id=contract.id,
        risk_finding_id=finding.id,
        event_type="risk_created",
        source="document_processing",
        summary="Automatic renewal risk detected.",
        previous_state=None,
        new_state={
            "severity": "high",
            "status": "open",
            "assessment_status": "confirmed",
        },
        evidence_snapshot=[
            {
                "evidence_type": "renewal_notice",
                "claim": "30 days notice required",
                "evidence_text": "Notice must be provided 30 days before renewal.",
            }
        ],
    )

    db_session.add(event)
    db_session.flush()

    return event


def test_investigation_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{uuid4()}/investigation"
    )

    assert response.status_code == 401


def test_investigation_forbidden_for_non_member(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{uuid4()}/investigation",
        headers=auth_headers(contract_api_data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_member_can_access_investigation(
    api_client,
    contract_api_data,
    db_session,
):
    contract = contract_api_data["contract_a"]

    finding = create_finding(db_session, contract)
    create_event(db_session, contract, finding)

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{finding.id}/investigation",
        headers=auth_headers(contract_api_data["member_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["risk_finding_id"] == str(finding.id)
    assert data["risk_overview"]["severity"] == "high"

    assert data["investigation_summary"]["total_events"] == 1

    assert len(data["timeline"]) == 1
    assert data["timeline"][0]["event_type"] == "risk_created"

    assert data["current_evidence"]["summary"]["total_linked"] == 0


def test_investigation_reconstructs_evidence_changes(
    api_client,
    contract_api_data,
    db_session,
):
    contract = contract_api_data["contract_a"]

    finding = create_finding(db_session, contract)

    event = RiskEvent(
        contract_id=contract.id,
        risk_finding_id=finding.id,
        event_type="evidence_changed",
        source="document_processing",
        summary="Supporting evidence changed.",
        previous_state={"evidence_count": 1},
        new_state={"evidence_count": 1},
        evidence_snapshot={
            "previous": [
                {"claim": "30 days notice"}
            ],
            "current": [
                {"claim": "60 days notice"}
            ],
        },
    )

    db_session.add(event)
    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{finding.id}/investigation",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["evidence_evolution"]) == 1

    evolution = data["evidence_evolution"][0]

    assert evolution["added"] == [
        {"claim": "60 days notice"}
    ]

    assert evolution["removed"] == [
        {"claim": "30 days notice"}
    ]


def test_investigation_hides_other_organization_findings(
    api_client,
    contract_api_data,
    db_session,
):
    contract = contract_api_data["contract_b"]

    finding = create_finding(db_session, contract)

    create_event(db_session, contract, finding)

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{finding.id}/investigation",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 404


def test_investigation_returns_404_for_missing_finding(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/"
        f"risk-findings/{uuid4()}/investigation",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 404