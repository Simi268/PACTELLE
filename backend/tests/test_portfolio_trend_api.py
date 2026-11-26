from datetime import datetime, timedelta, timezone

from app.models.portfolio_analysis_snapshot import (
    PortfolioAnalysisSnapshot,
    PortfolioAnalysisSnapshotFinding,
)

from tests.test_portfolio_finding_api import auth_headers


def trend_url(organization_id, limit=None):
    url = (
        f"/api/v1/organizations/{organization_id}"
        "/portfolio-risk-trends"
    )
    if limit is not None:
        url += f"?limit={limit}"
    return url


def create_snapshot(
    db,
    organization_id,
    created_at,
    findings=None,
):
    findings = findings or []

    snapshot = PortfolioAnalysisSnapshot(
        organization_id=organization_id,
        analysis_version="1.0",
        total_contracts=2,
        total_obligations=4,
        total_comparisons=2,
        total_findings=len(findings),
        summary={},
        created_at=created_at,
    )

    db.add(snapshot)
    db.flush()

    for finding in findings:
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
                assessment_status=finding.get(
                    "assessment_status", "provisional"
                ),
                details={},
                contract_ids=[],
                evidence_ids=[],
                captured_at=created_at,
            )
        )

    db.flush()
    return snapshot


def test_portfolio_trends_requires_authentication(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        trend_url(contract_api_data["organization_a"].id)
    )

    assert response.status_code == 401


def test_member_can_access_portfolio_risk_trends(
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
        trend_url(organization_id),
        headers=auth_headers(data["member_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["organization_id"] == str(organization_id)
    assert result["snapshot_count"] == 2
    assert result["overall_trend"] == "increasing"

    assert result["risk_score"]["initial"] == 5
    assert result["risk_score"]["latest"] == 6
    assert result["risk_score"]["change"] == 1

    assert result["finding_count"]["initial"] == 2
    assert result["finding_count"]["latest"] == 2

    patterns = {
        item["rule_id"]: item
        for item in result["risk_patterns"]
    }

    assert patterns["RULE-001"]["classification"] == "persistent"
    assert patterns["RULE-002"]["detected_in_latest_snapshot"] is False
    assert patterns["RULE-003"]["classification"] == "emerging"

    assert result["human_review_required"] is True


def test_rejects_outsider_access_to_portfolio_risk_trends(
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
        trend_url(data["organization_a"].id),
        headers=auth_headers(data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_portfolio_trends_requires_at_least_two_snapshots(
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
        trend_url(data["organization_a"].id),
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 409
