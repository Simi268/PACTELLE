from datetime import datetime, timezone

from app.core.security import create_access_token

from app.models.risk_event import RiskEvent
from app.models.risk_finding import RiskFinding


def auth_headers(user):
    token = create_access_token(user.id)

    return {
        "Authorization": f"Bearer {token}"
    }


def create_finding(db_session, contract):
    finding = RiskFinding(
        contract_id=contract.id,
        risk_type="automatic_renewal",
        title="Automatic Renewal Risk",
        description="Contract contains an automatic renewal clause.",
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


def create_event(
    db_session,
    contract,
    finding,
    event_type="risk_created",
    summary="Risk detected.",
):
    event = RiskEvent(
        contract_id=contract.id,
        risk_finding_id=finding.id if finding else None,
        event_type=event_type,
        source="system",
        summary=summary,
        previous_state=None,
        new_state={
            "severity": "high",
            "status": "open",
        },
        evidence_snapshot=[
            {
                "evidence_type": "renewal_notice",
                "claim": "30 days notice required",
            }
        ],
    )

    db_session.add(event)
    db_session.flush()

    return event


def test_risk_events_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events"
    )

    assert response.status_code == 401


def test_risk_events_forbidden_for_non_member(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        headers=auth_headers(contract_api_data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_member_can_access_risk_event_timeline(
    api_client,
    contract_api_data,
    db_session,
):
    finding = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding,
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        headers=auth_headers(contract_api_data["member_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1

    assert len(data["events"]) == 1

    event = data["events"][0]

    assert event["event_type"] == "risk_created"
    assert event["summary"] == "Risk detected."
    assert event["evidence_snapshot"] is not None


def test_risk_events_are_isolated_by_organization(
    api_client,
    contract_api_data,
    db_session,
):
    finding_a = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    finding_b = create_finding(
        db_session,
        contract_api_data["contract_b"],
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding_a,
    )

    create_event(
        db_session,
        contract_api_data["contract_b"],
        finding_b,
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    events = response.json()["events"]

    assert len(events) == 1

    assert (
        events[0]["contract_id"]
        == str(contract_api_data["contract_a"].id)
    )


def test_risk_events_filter_by_contract(
    api_client,
    contract_api_data,
    db_session,
):
    finding_a = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding_a,
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        params={
            "contract_id": str(
                contract_api_data["empty_contract"].id
            )
        },
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_risk_events_filter_by_finding(
    api_client,
    contract_api_data,
    db_session,
):
    finding = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding,
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        params={
            "risk_finding_id": str(finding.id)
        },
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_risk_events_filter_by_event_type(
    api_client,
    contract_api_data,
    db_session,
):
    finding = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding,
        event_type="risk_created",
    )

    create_event(
        db_session,
        contract_api_data["contract_a"],
        finding,
        event_type="evidence_changed",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        params={
            "event_type": "evidence_changed"
        },
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["events"][0]["event_type"] == "evidence_changed"


def test_risk_events_pagination(
    api_client,
    contract_api_data,
    db_session,
):
    finding = create_finding(
        db_session,
        contract_api_data["contract_a"],
    )

    for index in range(5):
        create_event(
            db_session,
            contract_api_data["contract_a"],
            finding,
            summary=f"Event {index}",
        )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        params={
            "page": 1,
            "page_size": 2,
        },
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 3
    assert len(data["events"]) == 2


def test_risk_events_reject_invalid_pagination(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/"
        f"{contract_api_data['organization_a'].id}/risk-events",
        params={
            "page": 0,
            "page_size": 200,
        },
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 422