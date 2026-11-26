from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.portfolio_evolution import (
    PortfolioEvolutionError,
    compare_portfolio_snapshots,
)


def make_finding(
    rule_id,
    severity="medium",
    status="open",
):
    return SimpleNamespace(
        rule_id=rule_id,
        severity=severity,
        finding_type="potential_conflict",
        title=f"Finding {rule_id}",
        status=status,
        assessment_status="provisional",
        contract_ids=["contract-1", "contract-2"],
        evidence_ids=["evidence-1", "evidence-2"],
    )


def make_snapshot(
    organization_id=None,
    findings=None,
    created_at=None,
):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id or uuid4(),
        created_at=created_at or datetime.now(timezone.utc),
        findings=findings or [],
    )


def compare(previous_findings, current_findings):
    organization_id = uuid4()

    previous_time = datetime.now(timezone.utc)
    current_time = previous_time + timedelta(minutes=5)

    previous = make_snapshot(
        organization_id=organization_id,
        findings=previous_findings,
        created_at=previous_time,
    )

    current = make_snapshot(
        organization_id=organization_id,
        findings=current_findings,
        created_at=current_time,
    )

    return compare_portfolio_snapshots(previous, current)


def test_detects_new_finding():
    result = compare(
        [],
        [make_finding("RULE-001")],
    )

    assert result["summary"]["new"] == 1
    assert result["summary"]["persistent"] == 0
    assert result["findings"][0]["evolution"] == "new"


def test_detects_persistent_finding():
    result = compare(
        [make_finding("RULE-001")],
        [make_finding("RULE-001")],
    )

    assert result["summary"]["persistent"] == 1
    assert result["findings"][0]["evolution"] == "persistent"


def test_detects_not_detected_finding():
    result = compare(
        [make_finding("RULE-001")],
        [],
    )

    assert result["summary"]["not_detected"] == 1
    assert result["findings"][0]["evolution"] == "not_detected"
    assert result["human_review_required"] is True


def test_detects_severity_increase():
    result = compare(
        [make_finding("RULE-001", severity="medium")],
        [make_finding("RULE-001", severity="critical")],
    )

    assert result["summary"]["severity_increased"] == 1

    finding = result["findings"][0]

    assert finding["evolution"] == "persistent"
    assert finding["severity_change"] == "increased"


def test_detects_severity_decrease():
    result = compare(
        [make_finding("RULE-001", severity="high")],
        [make_finding("RULE-001", severity="low")],
    )

    assert result["summary"]["severity_decreased"] == 1
    assert result["findings"][0]["severity_change"] == "decreased"


def test_detects_unchanged_severity():
    result = compare(
        [make_finding("RULE-001", severity="medium")],
        [make_finding("RULE-001", severity="medium")],
    )

    assert result["summary"]["severity_unchanged"] == 1
    assert result["findings"][0]["severity_change"] == "unchanged"


def test_combines_multiple_evolution_changes():
    result = compare(
        [
            make_finding("RULE-001", "medium"),
            make_finding("RULE-002", "high"),
            make_finding("RULE-003", "low"),
        ],
        [
            make_finding("RULE-001", "critical"),
            make_finding("RULE-003", "low"),
            make_finding("RULE-004", "medium"),
        ],
    )

    summary = result["summary"]

    assert summary["new"] == 1
    assert summary["persistent"] == 2
    assert summary["not_detected"] == 1
    assert summary["severity_increased"] == 1
    assert summary["severity_unchanged"] == 1


def test_does_not_mark_not_detected_finding_as_resolved():
    previous_finding = make_finding(
        "RULE-001",
        status="open",
    )

    result = compare(
        [previous_finding],
        [],
    )

    assert result["findings"][0]["evolution"] == "not_detected"

    # The original finding remains untouched.
    assert previous_finding.status == "open"


def test_rejects_different_organizations():
    previous = make_snapshot()
    current = make_snapshot()

    with pytest.raises(
        PortfolioEvolutionError,
        match="different organizations",
    ):
        compare_portfolio_snapshots(previous, current)


def test_rejects_comparing_snapshot_with_itself():
    snapshot = make_snapshot()

    with pytest.raises(
        PortfolioEvolutionError,
        match="itself",
    ):
        compare_portfolio_snapshots(snapshot, snapshot)


def test_rejects_reversed_snapshot_order():
    organization_id = uuid4()
    now = datetime.now(timezone.utc)

    previous = make_snapshot(
        organization_id=organization_id,
        created_at=now + timedelta(minutes=5),
    )

    current = make_snapshot(
        organization_id=organization_id,
        created_at=now,
    )

    with pytest.raises(
        PortfolioEvolutionError,
        match="older",
    ):
        compare_portfolio_snapshots(previous, current)


def test_rejects_duplicate_rule_ids():
    previous = make_snapshot(
        findings=[
            make_finding("RULE-001"),
            make_finding("RULE-001"),
        ],
    )

    current = make_snapshot(
        organization_id=previous.organization_id,
        created_at=previous.created_at + timedelta(minutes=5),
    )

    with pytest.raises(
        PortfolioEvolutionError,
        match="Duplicate rule ID",
    ):
        compare_portfolio_snapshots(previous, current)