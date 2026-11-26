from typing import Any


PRIORITY_BY_SEVERITY = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

RECOMMENDATIONS = {
    "potential_conflict": [
        {
            "title": "Review the potentially conflicting obligations",
            "description": (
                "Have an authorized contract reviewer compare the linked clauses "
                "and determine whether the obligations can be satisfied together."
            ),
            "rationale": (
                "The portfolio analysis identified a potential operational dependency. "
                "The finding is not a legal conclusion and requires human assessment."
            ),
        },
        {
            "title": "Agree an operational owner and resolution plan",
            "description": (
                "Identify the business owner for the affected obligations and document "
                "a practical coordination plan, including responsible parties and dates."
            ),
            "rationale": (
                "Coordinating the parties responsible for related obligations can reduce "
                "the chance of missed notices, approvals, or implementation steps."
            ),
        },
    ],
    "similarity": [
        {
            "title": "Validate whether the similar terms are intentionally aligned",
            "description": (
                "Compare the linked contract clauses and confirm whether the similar "
                "terms reflect an intentional standard or require different treatment."
            ),
            "rationale": (
                "Similar wording can indicate standardization, but the business context "
                "and exact obligations should be reviewed before drawing a conclusion."
            ),
        },
    ],
    "repeated_risk": [
        {
            "title": "Investigate the recurring risk pattern",
            "description": (
                "Review the linked contracts and evidence to identify the common cause, "
                "affected process, and any existing controls."
            ),
            "rationale": (
                "A repeated pattern may indicate a process-level issue that is better "
                "addressed consistently across the portfolio."
            ),
        },
    ],
    "exposure_concentration": [
        {
            "title": "Assess and reduce concentrated contractual exposure",
            "description": (
                "Review the contracts contributing to the concentration and assess "
                "whether exposure can be diversified, limited, or monitored."
            ),
            "rationale": (
                "Concentrated exposure can increase the impact of a single counterparty "
                "or obligation failure."
            ),
        },
    ],
}


def recommend_actions(finding: Any) -> list[dict[str, Any]]:
    """Return deterministic, reviewable action proposals for a portfolio finding."""
    finding_type = getattr(finding, "finding_type", None)
    severity = getattr(finding, "severity", "medium")
    assessment_status = getattr(finding, "assessment_status", "provisional")

    templates = RECOMMENDATIONS.get(finding_type, [])
    priority = PRIORITY_BY_SEVERITY.get(severity, "medium")

    details = getattr(finding, "details", None) or {}
    uncertainty_note = ""
    if assessment_status != "confirmed":
        uncertainty_note = (
            " This finding is provisional; verify the underlying evidence and "
            "assessment before treating the recommendation as a confirmed requirement."
        )

    results = []
    for template in templates:
        results.append({
            **template,
            "priority": priority,
            "rationale": template["rationale"] + uncertainty_note,
            "due_days": {
                "critical": 2,
                "high": 7,
                "medium": 21,
                "low": 45,
            }.get(priority, 21),
            "requires_human_review": True,
            "finding_assessment_status": assessment_status,
            "legal_conclusion": False,
            "source_rule_id": getattr(finding, "rule_id", None),
            "finding_details": details,
        })

    return results
