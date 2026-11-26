from collections import Counter
from typing import Any

SEVERITY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class PortfolioEvolutionError(ValueError):
    """Raised when portfolio snapshots cannot be compared."""


def _index_findings(snapshot) -> dict[str, Any]:
    """
    Index snapshot findings by their deterministic rule ID.
    """
    findings = {}

    for finding in snapshot.findings:
        if finding.rule_id in findings:
            raise PortfolioEvolutionError(
                f"Duplicate rule ID in snapshot: {finding.rule_id}"
            )

        findings[finding.rule_id] = finding

    return findings


def _compare_severity(previous_severity, current_severity):
    """
    Compare severity without modifying either finding.
    """
    previous_rank = SEVERITY_ORDER.get(previous_severity)
    current_rank = SEVERITY_ORDER.get(current_severity)

    if previous_rank is None or current_rank is None:
        return "unknown"

    if current_rank > previous_rank:
        return "increased"

    if current_rank < previous_rank:
        return "decreased"

    return "unchanged"


def compare_portfolio_snapshots(
    previous_snapshot,
    current_snapshot,
) -> dict:
    """
    Compare two portfolio analysis snapshots.

    Evolution classifications:
    - new
    - persistent
    - not_detected

    Severity changes:
    - increased
    - decreased
    - unchanged
    - unknown

    This service never resolves or updates live findings.
    """

    if previous_snapshot.organization_id != current_snapshot.organization_id:
        raise PortfolioEvolutionError(
            "Cannot compare snapshots belonging to different organizations."
        )

    if previous_snapshot.id == current_snapshot.id:
        raise PortfolioEvolutionError(
            "Cannot compare a snapshot with itself."
        )

    if previous_snapshot.created_at > current_snapshot.created_at:
        raise PortfolioEvolutionError(
            "Previous snapshot must be older than current snapshot."
        )

    previous_findings = _index_findings(previous_snapshot)
    current_findings = _index_findings(current_snapshot)

    previous_rule_ids = set(previous_findings)
    current_rule_ids = set(current_findings)

    new_rule_ids = current_rule_ids - previous_rule_ids
    persistent_rule_ids = current_rule_ids & previous_rule_ids
    not_detected_rule_ids = previous_rule_ids - current_rule_ids

    results = []

    # Newly detected findings.
    for rule_id in sorted(new_rule_ids):
        finding = current_findings[rule_id]

        results.append({
            "rule_id": rule_id,
            "evolution": "new",
            "severity_change": None,
            "previous_severity": None,
            "current_severity": finding.severity,
            "finding_type": finding.finding_type,
            "title": finding.title,
            "status": finding.status,
            "assessment_status": finding.assessment_status,
            "contract_ids": finding.contract_ids or [],
            "evidence_ids": finding.evidence_ids or [],
        })

    # Findings present in both snapshots.
    for rule_id in sorted(persistent_rule_ids):
        previous = previous_findings[rule_id]
        current = current_findings[rule_id]

        results.append({
            "rule_id": rule_id,
            "evolution": "persistent",
            "severity_change": _compare_severity(
                previous.severity,
                current.severity,
            ),
            "previous_severity": previous.severity,
            "current_severity": current.severity,
            "finding_type": current.finding_type,
            "title": current.title,
            "status": current.status,
            "assessment_status": current.assessment_status,
            "contract_ids": current.contract_ids or [],
            "evidence_ids": current.evidence_ids or [],
        })

    # Findings that disappeared from the latest analysis.
    for rule_id in sorted(not_detected_rule_ids):
        finding = previous_findings[rule_id]

        results.append({
            "rule_id": rule_id,
            "evolution": "not_detected",
            "severity_change": None,
            "previous_severity": finding.severity,
            "current_severity": None,
            "finding_type": finding.finding_type,
            "title": finding.title,
            "status": finding.status,
            "assessment_status": finding.assessment_status,
            "contract_ids": finding.contract_ids or [],
            "evidence_ids": finding.evidence_ids or [],
        })

    evolution_counts = Counter(
        item["evolution"] for item in results
    )

    severity_counts = Counter(
        item["severity_change"]
        for item in results
        if item["severity_change"] is not None
    )

    return {
        "organization_id": str(current_snapshot.organization_id),
        "previous_snapshot_id": str(previous_snapshot.id),
        "current_snapshot_id": str(current_snapshot.id),
        "previous_snapshot_created_at": previous_snapshot.created_at,
        "current_snapshot_created_at": current_snapshot.created_at,
        "summary": {
            "previous_findings": len(previous_findings),
            "current_findings": len(current_findings),
            "new": evolution_counts["new"],
            "persistent": evolution_counts["persistent"],
            "not_detected": evolution_counts["not_detected"],
            "severity_increased": severity_counts["increased"],
            "severity_decreased": severity_counts["decreased"],
            "severity_unchanged": severity_counts["unchanged"],
            "severity_unknown": severity_counts["unknown"],
        },
        "findings": results,
        "human_review_required": bool(not_detected_rule_ids),
    }