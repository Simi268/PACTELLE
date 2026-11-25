from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.services.risk_event_service import (
    build_risk_snapshot,
    build_evidence_snapshot,
    record_risk_changes,
)


def make_finding(**overrides):
    data = {
        "id": uuid4(),
        "contract_id": uuid4(),
        "risk_type": "renewal_exposure",
        "title": "Automatic Renewal Exposure",
        "description": "Automatic renewal detected.",
        "severity": "medium",
        "status": "open",
        "assessment_status": "provisional",
        "deadline_date": date(2027, 3, 15),
        "confidence": None,
        "rule_id": "RENEWAL-001",
        "rule_version": "1.0",
    }

    data.update(overrides)

    return SimpleNamespace(**data)


class FakeDB:

    def __init__(self):
        self.events = []

    def add(self, event):
        self.events.append(event)


def test_build_risk_snapshot():
    finding = make_finding()

    snapshot = build_risk_snapshot(finding)

    assert snapshot["severity"] == "medium"
    assert snapshot["status"] == "open"
    assert snapshot["assessment_status"] == "provisional"
    assert snapshot["deadline_date"] == "2027-03-15"


def test_risk_creation_generates_event():
    db = FakeDB()
    finding = make_finding()

    events = record_risk_changes(
        db,
        finding,
        previous_state=None,
    )

    assert len(events) == 1
    assert events[0].event_type == "risk_created"


def test_severity_change_generates_event():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    finding.severity = "high"

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert len(events) == 1
    assert events[0].event_type == "severity_changed"
    assert events[0].previous_state["severity"] == "medium"
    assert events[0].new_state["severity"] == "high"


def test_assessment_change_generates_event():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    finding.assessment_status = "confirmed"

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert len(events) == 1
    assert events[0].event_type == "assessment_changed"


def test_deadline_change_generates_event():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    finding.deadline_date = date(2027, 3, 10)

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert len(events) == 1
    assert events[0].event_type == "deadline_changed"


def test_risk_resolution_generates_event():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    finding.status = "resolved"

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert len(events) == 1
    assert events[0].event_type == "risk_resolved"


def test_risk_reopening_generates_event():
    db = FakeDB()
    finding = make_finding(status="open")

    previous = build_risk_snapshot(finding)
    previous["status"] = "resolved"

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert len(events) == 1
    assert events[0].event_type == "risk_reopened"


def test_multiple_changes_generate_separate_events():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    finding.severity = "high"
    finding.assessment_status = "confirmed"

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    event_types = {
        event.event_type
        for event in events
    }

    assert event_types == {
        "severity_changed",
        "assessment_changed",
    }


def test_unchanged_state_generates_no_events():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
    )

    assert events == []


def test_evidence_snapshot_preserves_details():
    evidence = SimpleNamespace(
        evidence_type="renewal_notice",
        claim="Notice period",
        evidence_text="30 days notice required.",
        verification_status="verified",
        confidence=0.95,
        extraction_method="rule_based",
        page_number=2,
        char_start=100,
        char_end=130,
    )

    snapshot = build_evidence_snapshot([evidence])

    assert len(snapshot) == 1
    assert snapshot[0]["evidence_type"] == "renewal_notice"
    assert snapshot[0]["verification_status"] == "verified"
    assert snapshot[0]["page_number"] == 2


def test_evidence_change_generates_event():
    db = FakeDB()
    finding = make_finding()

    previous = build_risk_snapshot(finding)

    old_evidence = [{
        "evidence_type": "renewal_notice",
        "claim": "Old notice",
        "evidence_text": "60 days notice.",
        "verification_status": "verified",
        "confidence": 0.9,
        "extraction_method": "rule_based",
        "page_number": 1,
        "char_start": 10,
        "char_end": 30,
    }]

    new_evidence = [{
        "evidence_type": "renewal_notice",
        "claim": "New notice",
        "evidence_text": "30 days notice.",
        "verification_status": "verified",
        "confidence": 0.95,
        "extraction_method": "rule_based",
        "page_number": 2,
        "char_start": 100,
        "char_end": 130,
    }]

    events = record_risk_changes(
        db,
        finding,
        previous_state=previous,
        previous_evidence=old_evidence,
        current_evidence=[
            SimpleNamespace(**item)
            for item in new_evidence
        ],
    )

    assert len(events) == 1
    assert events[0].event_type == "evidence_changed"


def test_event_does_not_commit_transaction():
    db = FakeDB()
    finding = make_finding()

    record_risk_changes(
        db,
        finding,
        previous_state=None,
    )

    assert len(db.events) == 1
    assert not hasattr(db, "commit")