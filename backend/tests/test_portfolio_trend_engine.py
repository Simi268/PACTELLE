from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.portfolio_trend_engine import (
    analyze_portfolio_risk_trends,
    PortfolioTrendError,
)


def make_finding(
    rule_id,
    severity="medium",
    status="open",
    assessment_status="provisional",
):
    return SimpleNamespace(
        rule_id=rule_id,
        finding_type="potential_conflict",
        title=f"Finding {rule_id}",
        severity=severity,
        status=status,
        assessment_status=assessment_status,
        contract_ids=["contract-1"],
        evidence_ids=["evidence-1"],
    )


def make_snapshot(organization_id, days_ago, findings):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        created_at=datetime.now(timezone.utc)
        - timedelta(days=days_ago),
        findings=findings,
    )


def test_detects_increasing_risk():
    org_id = uuid4()

    older = make_snapshot(
        org_id, 10, [make_finding("R1", "low")]
    )
    newer = make_snapshot(
        org_id, 5, [make_finding("R1", "critical")]
    )

    result = analyze_portfolio_risk_trends([older, newer])

    assert result["overall_trend"] == "increasing"
    assert result["risk_score"]["change"] == 3


def test_detects_decreasing_risk():
    org_id = uuid4()

    older = make_snapshot(
        org_id, 10, [make_finding("R1", "critical")]
    )
    newer = make_snapshot(
        org_id, 5, [make_finding("R1", "low")]
    )

    result = analyze_portfolio_risk_trends([older, newer])

    assert result["overall_trend"] == "decreasing"


def test_detects_stable_risk():
    org_id = uuid4()

    older = make_snapshot(
        org_id, 10, [make_finding("R1", "high")]
    )
    newer = make_snapshot(
        org_id, 5, [make_finding("R1", "high")]
    )

    result = analyze_portfolio_risk_trends([older, newer])

    assert result["overall_trend"] == "stable"


def test_detects_persistent_risk():
    org_id = uuid4()

    snapshots = [
        make_snapshot(
            org_id, days, [make_finding("R1")]
        )
        for days in [15, 10, 5]
    ]

    result = analyze_portfolio_risk_trends(snapshots)

    assert result["classification_summary"]["persistent"] == 1


def test_detects_emerging_risk():
    org_id = uuid4()

    older = make_snapshot(org_id, 10, [])
    newer = make_snapshot(
        org_id, 5, [make_finding("R1")]
    )

    result = analyze_portfolio_risk_trends([older, newer])

    assert result["classification_summary"]["emerging"] == 1


def test_detects_recurring_risk():
    org_id = uuid4()

    snapshots = [
        make_snapshot(
            org_id, 15, [make_finding("R1")]
        ),
        make_snapshot(org_id, 10, []),
        make_snapshot(
            org_id, 5, [make_finding("R1")]
        ),
    ]

    result = analyze_portfolio_risk_trends(snapshots)

    assert result["classification_summary"]["recurring"] == 1


def test_detects_risk_not_present_in_latest_snapshot():
    org_id = uuid4()

    snapshots = [
        make_snapshot(
            org_id, 15, [make_finding("R1")]
        ),
        make_snapshot(org_id, 10, []),
        make_snapshot(org_id, 5, []),
    ]

    result = analyze_portfolio_risk_trends(snapshots)

    assert (
        result["classification_summary"]["not_detected_in_latest"]
        == 1
    )


def test_sorts_snapshots_chronologically():
    org_id = uuid4()

    older = make_snapshot(org_id, 10, [])
    newer = make_snapshot(org_id, 5, [])

    result = analyze_portfolio_risk_trends([newer, older])

    assert result["first_snapshot_id"] == older.id
    assert result["latest_snapshot_id"] == newer.id


def test_rejects_single_snapshot():
    snapshot = make_snapshot(uuid4(), 5, [])

    with pytest.raises(PortfolioTrendError):
        analyze_portfolio_risk_trends([snapshot])


def test_rejects_different_organizations():
    snapshots = [
        make_snapshot(uuid4(), 10, []),
        make_snapshot(uuid4(), 5, []),
    ]

    with pytest.raises(PortfolioTrendError):
        analyze_portfolio_risk_trends(snapshots)


def test_rejects_duplicate_rule_ids():
    org_id = uuid4()

    snapshot = make_snapshot(
        org_id,
        10,
        [
            make_finding("R1"),
            make_finding("R1"),
        ],
    )

    newer = make_snapshot(org_id, 5, [])

    with pytest.raises(PortfolioTrendError):
        analyze_portfolio_risk_trends([snapshot, newer])


def test_requires_human_review_for_provisional_findings():
    org_id = uuid4()

    snapshots = [
        make_snapshot(
            org_id, 10,
            [make_finding("R1", assessment_status="provisional")],
        ),
        make_snapshot(
            org_id, 5,
            [make_finding("R1", assessment_status="provisional")],
        ),
    ]

    result = analyze_portfolio_risk_trends(snapshots)

    assert result["human_review_required"] is True