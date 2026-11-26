from collections import defaultdict
from typing import Any


SEVERITY_WEIGHTS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SEVERITY_LEVELS = (
    "critical",
    "high",
    "medium",
    "low",
)


class PortfolioTrendError(Exception):
    """Raised when portfolio trend analysis cannot be performed."""


def _severity_distribution(findings):
    distribution = {
        severity: 0
        for severity in SEVERITY_LEVELS
    }

    for finding in findings:
        severity = finding.severity

        if severity not in distribution:
            raise PortfolioTrendError(
                f"Unsupported finding severity: {severity}"
            )

        distribution[severity] += 1

    return distribution


def _risk_score(distribution):
    """Return a comparative weighted count, not a probability."""
    return sum(
        distribution[severity] * SEVERITY_WEIGHTS[severity]
        for severity in SEVERITY_LEVELS
    )


def _index_findings(snapshot):
    indexed = {}

    for finding in snapshot.findings:
        if finding.rule_id in indexed:
            raise PortfolioTrendError(
                f"Duplicate rule ID in snapshot: {finding.rule_id}"
            )

        indexed[finding.rule_id] = finding

    return indexed


def _calculate_direction(previous, current):
    if current > previous:
        return "increasing"

    if current < previous:
        return "decreasing"

    return "stable"


def analyze_portfolio_risk_trends(
    snapshots: list[Any],
) -> dict[str, Any]:
    """
    Analyze portfolio risk trends using immutable historical snapshots.

    Snapshots must expose:
      - id
      - organization_id
      - created_at
      - findings

    Each historical finding must expose:
      - rule_id, finding_type, title, severity, status,
        assessment_status, contract_ids, evidence_ids

    Snapshots may be supplied in any order. Risk classification and
    latest-snapshot detection are reported independently: a risk can
    be recurring historically while not appearing in the latest snapshot.
    """

    if len(snapshots) < 2:
        raise PortfolioTrendError(
            "At least two snapshots are required for trend analysis."
        )

    organization_ids = {
        snapshot.organization_id
        for snapshot in snapshots
    }

    if len(organization_ids) != 1:
        raise PortfolioTrendError(
            "All snapshots must belong to the same organization."
        )

    snapshots = sorted(
        snapshots,
        key=lambda snapshot: (
            snapshot.created_at,
            str(snapshot.id),
        ),
    )

    snapshot_ids = [snapshot.id for snapshot in snapshots]

    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise PortfolioTrendError(
            "Duplicate snapshots cannot be analyzed."
        )

    indexed_snapshots = [
        _index_findings(snapshot)
        for snapshot in snapshots
    ]

    risk_history = defaultdict(list)
    snapshot_metrics = []

    for index, snapshot in enumerate(snapshots):
        findings = list(snapshot.findings)
        distribution = _severity_distribution(findings)

        snapshot_metrics.append({
            "snapshot_id": snapshot.id,
            "created_at": snapshot.created_at,
            "total_findings": len(findings),
            "severity_distribution": distribution,
            "weighted_risk_score": _risk_score(distribution),
        })

        for rule_id, finding in indexed_snapshots[index].items():
            risk_history[rule_id].append({
                "snapshot_index": index,
                "snapshot_id": snapshot.id,
                "created_at": snapshot.created_at,
                "finding_type": finding.finding_type,
                "title": finding.title,
                "severity": finding.severity,
                "status": finding.status,
                "assessment_status": finding.assessment_status,
                "contract_ids": finding.contract_ids or [],
                "evidence_ids": finding.evidence_ids or [],
            })

    first_metrics = snapshot_metrics[0]
    latest_metrics = snapshot_metrics[-1]

    score_delta = (
        latest_metrics["weighted_risk_score"]
        - first_metrics["weighted_risk_score"]
    )
    finding_delta = (
        latest_metrics["total_findings"]
        - first_metrics["total_findings"]
    )

    risk_patterns = []

    classification_counts = {
        "emerging": 0,
        "persistent": 0,
        "recurring": 0,
        "not_detected_in_latest": 0,
        "intermittent": 0,
    }

    for rule_id, history in risk_history.items():
        appearances = len(history)
        first_seen_index = history[0]["snapshot_index"]
        last_seen_index = history[-1]["snapshot_index"]

        detected_in_latest = (
            last_seen_index == len(snapshots) - 1
        )

        if appearances == 1 and detected_in_latest:
            classification = "emerging"
        elif appearances == len(snapshots):
            classification = "persistent"
        elif appearances >= 2:
            classification = "recurring"
        elif not detected_in_latest:
            # Retained for a risk seen once historically but absent
            # from the latest snapshot.
            classification = "not_detected_in_latest"
        else:
            classification = "intermittent"

        classification_counts[classification] += 1

        # This count is deliberately independent of classification.
        # A recurring risk can also be absent from the latest snapshot.
        if not detected_in_latest and classification != "not_detected_in_latest":
            classification_counts["not_detected_in_latest"] += 1

        latest_observation = history[-1]

        risk_patterns.append({
            "rule_id": rule_id,
            "title": latest_observation["title"],
            "finding_type": latest_observation["finding_type"],
            "classification": classification,
            "appearances": appearances,
            "total_snapshots": len(snapshots),
            "first_detected_at": history[0]["created_at"],
            "last_detected_at": latest_observation["created_at"],
            "detected_in_latest_snapshot": detected_in_latest,
            "latest_severity": latest_observation["severity"],
            "severity_history": [
                item["severity"]
                for item in history
            ],
            "status_history": [
                item["status"]
                for item in history
            ],
            "assessment_status_history": [
                item["assessment_status"]
                for item in history
            ],
            "contract_ids": latest_observation["contract_ids"],
            "evidence_ids": latest_observation["evidence_ids"],
            "human_review_required": (
                not detected_in_latest
                or any(
                    item["assessment_status"] != "confirmed"
                    for item in history
                )
            ),
        })

    risk_patterns.sort(
        key=lambda item: (
            -item["appearances"],
            item["rule_id"],
        )
    )

    overall_direction = _calculate_direction(
        first_metrics["weighted_risk_score"],
        latest_metrics["weighted_risk_score"],
    )

    return {
        "organization_id": next(iter(organization_ids)),
        "snapshot_count": len(snapshots),
        "first_snapshot_id": first_metrics["snapshot_id"],
        "latest_snapshot_id": latest_metrics["snapshot_id"],
        "overall_trend": overall_direction,
        "risk_score": {
            "initial": first_metrics["weighted_risk_score"],
            "latest": latest_metrics["weighted_risk_score"],
            "change": score_delta,
            "direction": overall_direction,
            "interpretation": (
                "Comparative weighted finding count; not a probability "
                "or legal-risk measurement."
            ),
        },
        "finding_count": {
            "initial": first_metrics["total_findings"],
            "latest": latest_metrics["total_findings"],
            "change": finding_delta,
        },
        "severity_distribution": {
            "initial": first_metrics["severity_distribution"],
            "latest": latest_metrics["severity_distribution"],
        },
        "classification_summary": classification_counts,
        "snapshot_history": snapshot_metrics,
        "risk_patterns": risk_patterns,
        "human_review_required": any(
            pattern["human_review_required"]
            for pattern in risk_patterns
        ),
    }
