from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.risk_investigation import (
    reconstruct_investigation,
    _compare_evidence,
)


def make_event(
    event_type,
    previous_state=None,
    new_state=None,
    evidence_snapshot=None,
):
    return SimpleNamespace(
        id="event-1",
        event_type=event_type,
        source="document_processing",
        actor_id=None,
        summary=f"Test {event_type}",
        previous_state=previous_state,
        new_state=new_state,
        evidence_snapshot=evidence_snapshot,
        created_at=datetime.now(timezone.utc),
    )


def make_finding(
    assessment_status="confirmed",
    status="open",
):
    return SimpleNamespace(
        id="finding-1",
        status=status,
        assessment_status=assessment_status,
        evidence_links=[],
        risk_type="automatic_renewal",
        title="Automatic Renewal Risk",
        description="Contract may renew automatically.",
        severity="high",
        deadline_date=None,
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0",
    )


def test_compare_evidence_identifies_added_and_removed():

    previous = [
        {"claim": "30 days notice"},
        {"claim": "Automatic renewal"},
    ]

    current = [
        {"claim": "60 days notice"},
        {"claim": "Automatic renewal"},
    ]

    result = _compare_evidence(previous, current)

    assert result["previous_count"] == 2
    assert result["current_count"] == 2

    assert result["added"] == [
        {"claim": "60 days notice"}
    ]

    assert result["removed"] == [
        {"claim": "30 days notice"}
    ]


def test_compare_evidence_handles_empty_snapshots():

    result = _compare_evidence([], [])

    assert result["added"] == []
    assert result["removed"] == []
    assert result["previous_count"] == 0
    assert result["current_count"] == 0


def test_compare_evidence_preserves_duplicate_counts():

    previous = [
        {"claim": "Notice"},
        {"claim": "Notice"},
    ]

    current = [
        {"claim": "Notice"},
    ]

    result = _compare_evidence(previous, current)

    assert len(result["removed"]) == 1
    assert result["added"] == []


def test_investigation_reconstructs_timeline():

    finding = make_finding()

    events = [
        make_event(
            "risk_created",
            new_state={"severity": "medium"},
        ),
        make_event(
            "severity_changed",
            previous_state={"severity": "medium"},
            new_state={"severity": "high"},
        ),
    ]

    result = reconstruct_investigation(
        finding,
        events,
    )

    assert result["investigation_summary"]["total_events"] == 2

    assert len(result["timeline"]) == 2

    assert len(result["assessment_evolution"]) == 1

    assert (
        result["assessment_evolution"][0]["event_type"]
        == "severity_changed"
    )


def test_investigation_reconstructs_evidence_evolution():

    finding = make_finding()

    event = make_event(
        "evidence_changed",
        evidence_snapshot={
            "previous": [
                {"claim": "30 days notice"}
            ],
            "current": [
                {"claim": "60 days notice"}
            ],
        },
    )

    result = reconstruct_investigation(
        finding,
        [event],
    )

    evolution = result["evidence_evolution"]

    assert len(evolution) == 1

    assert evolution[0]["added"] == [
        {"claim": "60 days notice"}
    ]

    assert evolution[0]["removed"] == [
        {"claim": "30 days notice"}
    ]


def test_investigation_flags_missing_history():

    finding = make_finding()

    result = reconstruct_investigation(
        finding,
        [],
    )

    assert result["investigation_summary"]["total_events"] == 0

    assert any(
        "No historical risk events" in question
        for question in result["unresolved_questions"]
    )


def test_provisional_assessment_requires_human_review():

    finding = make_finding(
        assessment_status="provisional",
    )

    result = reconstruct_investigation(
        finding,
        [],
    )

    assert result["human_review_required"] is True

    assert any(
        "not been confirmed" in question
        for question in result["unresolved_questions"]
    )