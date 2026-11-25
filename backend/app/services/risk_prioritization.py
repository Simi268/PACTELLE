from datetime import date


def classify_urgency(deadline_date, today=None):
    today = today or date.today()

    if deadline_date is None:
        return "unknown"

    days_remaining = (deadline_date - today).days

    if days_remaining < 0:
        return "overdue"
    if days_remaining == 0:
        return "due_today"
    if days_remaining <= 7:
        return "immediate"
    if days_remaining <= 30:
        return "approaching"
    if days_remaining <= 90:
        return "upcoming"

    return "distant"


def identify_attention_flags(finding, scoring):
    flags = []

    if finding.severity in ("critical", "high"):
        if (
            scoring["evidence_confidence"] is None
            or scoring["evidence_confidence"] < 0.70
            or finding.assessment_status == "provisional"
        ):
            flags.append("high_impact_low_confidence")

    if scoring["evidence"]["total"] == 0:
        flags.append("missing_supporting_evidence")

    if scoring["evidence"]["missing_or_incomplete"]:
        flags.append("evidence_requires_review")

    return flags


def build_investigation_recommendation(
    finding,
    urgency,
    flags,
):
    reasons = []

    if urgency == "overdue":
        reasons.append("The contractual deadline has passed.")

    elif urgency == "due_today":
        reasons.append("The contractual deadline is today.")

    elif urgency == "immediate":
        reasons.append("The deadline is within seven days.")

    elif urgency == "approaching":
        reasons.append("The deadline is within 30 days.")

    if finding.severity == "critical":
        reasons.append("The finding has critical severity.")

    elif finding.severity == "high":
        reasons.append("The finding has high severity.")

    if "high_impact_low_confidence" in flags:
        reasons.append(
            "A potentially high-impact finding has insufficient "
            "or unverified supporting evidence."
        )

    if "missing_supporting_evidence" in flags:
        reasons.append(
            "Supporting evidence is missing and needs investigation."
        )

    if not reasons:
        reasons.append(
            "Review this finding according to its risk score and "
            "supporting evidence."
        )

    return {
        "investigation_priority": (
            "immediate"
            if urgency in ("overdue", "due_today", "immediate")
            or finding.severity == "critical"
            else "high"
            if finding.severity == "high"
            else "normal"
        ),
        "recommended_action": (
            "Verify the contractual clause and supporting evidence."
            if flags
            else "Review the contractual obligation and confirm "
                 "whether further action is required."
        ),
        "reasons": reasons,
    }