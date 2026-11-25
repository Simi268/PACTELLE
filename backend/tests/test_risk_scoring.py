from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.risk_scoring import (
    calculate_risk_score,
    calculate_deadline_urgency,
    calculate_priority,
)


def make_finding(
    severity="medium",
    deadline_date=None,
):
    return SimpleNamespace(
        severity=severity,
        deadline_date=deadline_date,
    )


def make_evidence(
    verification_status="unverified",
    confidence=0.8,
):
    return SimpleNamespace(
        verification_status=verification_status,
        confidence=confidence,
    )


def test_critical_risk_has_higher_score_than_low_risk():

    evidence = [
        make_evidence("verified", 0.9),
        make_evidence("verified", 0.9),
    ]

    critical = calculate_risk_score(
        make_finding("critical"),
        evidence,
        today=date(2026, 1, 1),
    )

    low = calculate_risk_score(
        make_finding("low"),
        evidence,
        today=date(2026, 1, 1),
    )

    assert critical["risk_score"] > low["risk_score"]


def test_overdue_deadline_has_maximum_urgency():

    result = calculate_deadline_urgency(
        date(2025, 12, 1),
        date(2026, 1, 1),
    )

    assert result == 100


def test_verified_evidence_has_higher_score():

    today = date(2026, 1, 1)

    verified = calculate_risk_score(
        make_finding(),
        [
            make_evidence("verified", 0.9),
            make_evidence("verified", 0.9),
        ],
        today,
    )

    unverified = calculate_risk_score(
        make_finding(),
        [
            make_evidence("unverified", 0.9),
            make_evidence("unverified", 0.9),
        ],
        today,
    )

    assert verified["risk_score"] > unverified["risk_score"]


def test_rejected_evidence_is_excluded():

    result = calculate_risk_score(
        make_finding(),
        [
            make_evidence("rejected", 0.99),
        ],
        date(2026, 1, 1),
    )

    assert result["evidence"]["total"] == 0
    assert result["evidence_confidence"] is None


def test_missing_evidence_is_reported():

    result = calculate_risk_score(
        make_finding(),
        [],
        date(2026, 1, 1),
    )

    assert result["evidence"]["total"] == 0
    assert len(result["evidence"]["missing_or_incomplete"]) > 0


def test_evidence_confidence_is_separate_from_risk_score():

    result = calculate_risk_score(
        make_finding("critical"),
        [
            make_evidence("verified", 0.7),
            make_evidence("verified", 0.9),
        ],
        date(2026, 1, 1),
    )

    assert result["risk_score"] is not None
    assert result["evidence_confidence"] == 0.8


@pytest.mark.parametrize(
    "score,expected",
    [
        (90, "critical"),
        (70, "high"),
        (50, "medium"),
        (20, "low"),
    ],
)
def test_priority_classification(score, expected):

    assert calculate_priority(score) == expected