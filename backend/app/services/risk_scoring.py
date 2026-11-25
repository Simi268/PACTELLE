from datetime import date

from app.models.risk_finding import RiskFinding


SEVERITY_WEIGHTS = {
    "critical": 100,
    "high": 80,
    "medium": 55,
    "low": 30,
}

SCORING_WEIGHTS = {
    "severity": 0.45,
    "deadline_urgency": 0.25,
    "evidence_completeness": 0.15,
    "verification": 0.10,
    "evidence_confidence": 0.05,
}


def calculate_deadline_urgency(deadline_date, today):
    if deadline_date is None:
        return 20

    days_remaining = (deadline_date - today).days

    if days_remaining <= 0:
        return 100
    if days_remaining <= 7:
        return 90
    if days_remaining <= 30:
        return 75
    if days_remaining <= 90:
        return 50

    return 20


def calculate_priority(score):
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"

    return "low"


def calculate_risk_score(
    finding: RiskFinding,
    evidence_records,
    today=None,
):
    """
    Calculate a transparent risk priority score.

    The score represents prioritization, not the probability
    that a legal or contractual event will occur.

    Evidence confidence is reported separately from the score.
    """

    today = today or date.today()

    severity_score = SEVERITY_WEIGHTS.get(
        finding.severity,
        30,
    )

    deadline_score = calculate_deadline_urgency(
        finding.deadline_date,
        today,
    )

    valid_evidence = [
        evidence
        for evidence in evidence_records
        if evidence.verification_status != "rejected"
    ]

    evidence_count = len(valid_evidence)

    # Two independent supporting records represent full
    # completeness for this initial scoring model.
    completeness_score = min(
        evidence_count / 2,
        1.0,
    ) * 100

    verified_records = [
        evidence
        for evidence in valid_evidence
        if evidence.verification_status == "verified"
    ]

    verification_score = (
        len(verified_records) / evidence_count * 100
        if evidence_count
        else 0
    )

    confidence_values = [
        evidence.confidence
        for evidence in valid_evidence
        if evidence.confidence is not None
    ]

    evidence_confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values
        else None
    )

    confidence_score = (
        evidence_confidence * 100
        if evidence_confidence is not None
        else 0
    )

    score = (
        severity_score * SCORING_WEIGHTS["severity"]
        + deadline_score * SCORING_WEIGHTS["deadline_urgency"]
        + completeness_score * SCORING_WEIGHTS["evidence_completeness"]
        + verification_score * SCORING_WEIGHTS["verification"]
        + confidence_score * SCORING_WEIGHTS["evidence_confidence"]
    )

    score = round(min(max(score, 0), 100), 2)

    missing_evidence = []

    if evidence_count == 0:
        missing_evidence.append(
            "No supporting evidence available."
        )

    if evidence_count < 2:
        missing_evidence.append(
            "Supporting evidence is incomplete."
        )

    if not verified_records:
        missing_evidence.append(
            "No supporting evidence has been verified."
        )

    if evidence_confidence is None:
        missing_evidence.append(
            "Evidence confidence is unavailable."
        )

    return {
        "risk_score": score,
        "priority": calculate_priority(score),

        # Separate from the risk score.
        "evidence_confidence": (
            round(evidence_confidence, 3)
            if evidence_confidence is not None
            else None
        ),

        "factors": {
            "severity": severity_score,
            "deadline_urgency": deadline_score,
            "evidence_completeness": round(
                completeness_score,
                2,
            ),
            "verification": round(
                verification_score,
                2,
            ),
            "evidence_confidence": round(
                confidence_score,
                2,
            ),
        },

        "evidence": {
            "total": evidence_count,
            "verified": len(verified_records),
            "missing_or_incomplete": missing_evidence,
        },

        "explanation": (
            f"This finding has a priority score of {score}/100. "
            f"Its contractual severity is {finding.severity}. "
            f"Deadline urgency contributes {deadline_score}/100. "
            f"{len(verified_records)} of {evidence_count} "
            "supporting evidence records are verified."
        ),
    }