from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.security import create_access_token
from app.models.portfolio_analysis_snapshot import (
    PortfolioAnalysisSnapshot,
    PortfolioAnalysisSnapshotFinding,
)

from tests.test_portfolio_finding_api import auth_headers


def evolution_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/portfolio-evolution"
    )


def create_snapshot(
    db,
    organization_id,
    created_at,
    findings=None,
):
    snapshot = PortfolioAnalysisSnapshot(
        organization_id=organization_id,
        analysis_version="1.0",
        total_contracts=2,
        total_obligations=4,
        total_comparisons=2,
        total_findings=len(findings or []),
        summary={},
        created_at=created_at,
    )

    db.add(snapshot)
    db.flush()

    for finding in findings or []:
        db.add(
            PortfolioAnalysisSnapshotFinding(
                snapshot_id=snapshot.id,
                portfolio_finding_id=None,
                rule_id=finding["rule_id"],
                finding_type="potential_conflict",
                title=finding["title"],
                description="Test finding",
                severity=finding["severity"],
                status="open",
                assessment_status="provisional",
                details={},
                contract_ids=[],
                evidence_ids=[],
                captured_at=created_at,
            )
        )

    db.flush()
    return snapshot


def test_evolution_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        evolution_url(
            contract_api_data["organization_a"].id
        )
    )

    assert response.status_code == 401


def test_member_can_access_portfolio_evolution(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    now = datetime.now(timezone.utc)

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now,
    )

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now + timedelta(minutes=5),
    )

    response = api_client.get(
        evolution_url(data["organization_a"].id),
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 200


def test_owner_can_access_portfolio_evolution(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    now = datetime.now(timezone.utc)

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now,
    )

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now + timedelta(minutes=5),
    )

    response = api_client.get(
        evolution_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200


def test_rejects_outsider_access(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    now = datetime.now(timezone.utc)

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now,
    )

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now + timedelta(minutes=5),
    )

    response = api_client.get(
        evolution_url(data["organization_a"].id),
        headers=auth_headers(data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_requires_at_least_two_snapshots(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_snapshot(
        db_session,
        data["organization_a"].id,
        datetime.now(timezone.utc),
    )

    response = api_client.get(
        evolution_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 409


def test_returns_correct_evolution(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    organization_id = data["organization_a"].id
    now = datetime.now(timezone.utc)

    create_snapshot(
        db_session,
        organization_id,
        now,
        findings=[
            {
                "rule_id": "RULE-001",
                "title": "Existing risk",
                "severity": "medium",
            },
            {
                "rule_id": "RULE-002",
                "title": "Disappearing risk",
                "severity": "high",
            },
        ],
    )

    create_snapshot(
        db_session,
        organization_id,
        now + timedelta(minutes=5),
        findings=[
            {
                "rule_id": "RULE-001",
                "title": "Existing risk",
                "severity": "critical",
            },
            {
                "rule_id": "RULE-003",
                "title": "New risk",
                "severity": "medium",
            },
        ],
    )

    response = api_client.get(
        evolution_url(organization_id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["organization_id"] == str(organization_id)

    assert result["summary"]["new"] == 1
    assert result["summary"]["persistent"] == 1
    assert result["summary"]["not_detected"] == 1

    assert result["summary"]["severity_increased"] == 1

    assert result["human_review_required"] is True


def test_does_not_modify_live_findings(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    now = datetime.now(timezone.utc)

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now,
        findings=[
            {
                "rule_id": "RULE-001",
                "title": "Previously detected risk",
                "severity": "high",
            }
        ],
    )

    create_snapshot(
        db_session,
        data["organization_a"].id,
        now + timedelta(minutes=5),
    )

    response = api_client.get(
        evolution_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    assert response.json()["summary"]["not_detected"] == 1