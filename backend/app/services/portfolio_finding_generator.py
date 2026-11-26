import hashlib
from typing import Any


GENERATOR_VERSION = "1.0"


def _build_rule_id(evidence_ids: list[str]) -> str:
    """
    Generate a stable identifier for the same evidence pair,
    regardless of comparison order.
    """

    normalized_ids = sorted(str(item) for item in evidence_ids)

    fingerprint = "|".join(normalized_ids)

    digest = hashlib.sha256(
        fingerprint.encode("utf-8")
    ).hexdigest()[:24]

    return f"portfolio_operational_dependency_{digest}"


def _extract_contracts(
    comparison: dict[str, Any],
) -> list[str]:

    contract_ids = {
        str(item["contract_id"])
        for item in comparison.get("evidence", [])
        if item.get("contract_id")
    }

    return sorted(contract_ids)


def _extract_evidence_ids(
    comparison: dict[str, Any],
) -> list[str]:

    evidence_ids = {
        str(item["evidence_id"])
        for item in comparison.get("evidence", [])
        if item.get("evidence_id")
    }

    return sorted(evidence_ids)


def _build_finding(
    comparison: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Generate a portfolio finding only for a potential
    operational dependency.

    Similarity and ordinary contractual variations are
    not automatically promoted to risk findings.
    """

    if (
        comparison.get("classification")
        != "potential_operational_dependency"
    ):
        return None

    if not comparison.get("operational_dependency_candidate"):
        return None

    contracts = _extract_contracts(comparison)
    evidence_ids = _extract_evidence_ids(comparison)

    if len(contracts) < 2 or len(evidence_ids) < 2:
        return None

    context = comparison.get("context_analysis") or {}

    rule_id = _build_rule_id(evidence_ids)

    obligation_type = comparison.get("obligation_type")

    return {
        "finding_type": "potential_conflict",
        "title": (
            f"Potential operational dependency: "
            f"{obligation_type}"
        ),
        "description": comparison.get("explanation"),
        "severity": "medium",
        "status": "open",
        "assessment_status": "provisional",
        "detection_method": "rule_based",
        "rule_id": rule_id,
        "rule_version": GENERATOR_VERSION,
        "confidence": None,
        "details": {
            "classification": "potential_operational_dependency",
            "obligation_type": obligation_type,
            "comparison_type": comparison.get(
                "comparison_type"
            ),
            "trigger_relationship": context.get(
                "trigger_relationship"
            ),
            "responsibility_relationship": context.get(
                "responsibility_relationship"
            ),
            "direction_relationship": context.get(
                "direction_relationship"
            ),
            "requires_human_review": True,
            "legal_conflict_established": False,
            "generator_version": GENERATOR_VERSION,
        },
        "contract_ids": contracts,
        "evidence_ids": evidence_ids,
    }


def generate_portfolio_findings(
    intelligence_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert unified portfolio intelligence into
    structured portfolio finding candidates.

    This function does not persist anything.

    Persistence, duplicate handling, and organization-level
    validation belong to the database service layer.
    """

    comparisons = intelligence_result.get("comparisons", [])

    findings = []
    skipped_comparisons = 0

    seen_rule_ids = set()

    for comparison in comparisons:

        finding = _build_finding(comparison)

        if finding is None:
            skipped_comparisons += 1
            continue

        if finding["rule_id"] in seen_rule_ids:
            skipped_comparisons += 1
            continue

        seen_rule_ids.add(finding["rule_id"])

        findings.append(finding)

    return {
        "summary": {
            "total_comparisons": len(comparisons),
            "generated_findings": len(findings),
            "skipped_comparisons": skipped_comparisons,
            "provisional_findings": sum(
                item["assessment_status"] == "provisional"
                for item in findings
            ),
            "human_review_required": len(findings),
        },
        "findings": findings,
    }