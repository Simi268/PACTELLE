from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.risk_event import RiskEvent


TRACKED_FIELDS = {
    "severity": "severity_changed",
    "status": "status_changed",
    "assessment_status": "assessment_changed",
    "deadline_date": "deadline_changed",
    "confidence": "confidence_changed",
}


def _serialize_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    return value


def build_risk_snapshot(finding):
    """
    Capture the current state of a risk finding.
    """

    return {
        "risk_type": finding.risk_type,
        "title": finding.title,
        "description": finding.description,
        "severity": finding.severity,
        "status": finding.status,
        "assessment_status": finding.assessment_status,
        "deadline_date": _serialize_value(
            finding.deadline_date
        ),
        "confidence": finding.confidence,
        "rule_id": finding.rule_id,
        "rule_version": finding.rule_version,
    }


def build_evidence_snapshot(evidence_records):
    """
    Preserve evidence details independently of live evidence records.

    This allows historical events to remain meaningful even when
    document reprocessing replaces evidence records.
    """

    snapshots = []

    for evidence in evidence_records or []:
        snapshots.append({
            "evidence_type": evidence.evidence_type,
            "claim": evidence.claim,
            "evidence_text": evidence.evidence_text,
            "verification_status": evidence.verification_status,
            "confidence": evidence.confidence,
            "extraction_method": evidence.extraction_method,
            "page_number": evidence.page_number,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
        })

    snapshots.sort(
        key=lambda item: (
            item["evidence_type"] or "",
            item["claim"] or "",
            item["evidence_text"] or "",
        )
    )

    return snapshots


def _create_event(
    db,
    finding,
    event_type,
    summary,
    previous_state,
    new_state,
    evidence_snapshot,
    source,
    actor_id,
):
    event = RiskEvent(
        risk_finding_id=finding.id,
        contract_id=finding.contract_id,
        event_type=event_type,
        source=source,
        actor_id=actor_id,
        summary=summary,
        previous_state=previous_state,
        new_state=new_state,
        evidence_snapshot=evidence_snapshot,
    )

    db.add(event)

    return event


def record_risk_event(
    db: Session,
    finding,
    event_type,
    summary,
    *,
    previous_state=None,
    new_state=None,
    evidence_snapshot=None,
    source="system",
    actor_id=None,
):
    """
    Record one risk event.

    Does not commit. Transaction ownership remains with the caller.
    """

    event = _create_event(
        db=db,
        finding=finding,
        event_type=event_type,
        summary=summary,
        previous_state=previous_state,
        new_state=new_state,
        evidence_snapshot=evidence_snapshot,
        source=source,
        actor_id=actor_id,
    )

    return event


def record_risk_changes(
    db: Session,
    finding,
    *,
    previous_state=None,
    previous_evidence=None,
    current_evidence=None,
    source="system",
    actor_id=None,
):
    """
    Compare previous and current risk states.

    Generates events for:
    - risk_created
    - severity_changed
    - status_changed
    - risk_resolved
    - risk_reopened
    - assessment_changed
    - deadline_changed
    - confidence_changed
    - evidence_changed

    Does not commit.
    """

    current_state = build_risk_snapshot(finding)

    current_evidence_snapshot = build_evidence_snapshot(
        current_evidence
    )

    events = []

    # First detection.
    if previous_state is None:

        events.append(
            _create_event(
                db=db,
                finding=finding,
                event_type="risk_created",
                summary=f"Risk detected: {finding.title}",
                previous_state=None,
                new_state=current_state,
                evidence_snapshot=current_evidence_snapshot,
                source=source,
                actor_id=actor_id,
            )
        )

        return events

    # Detect individual state changes.
    for field, event_type in TRACKED_FIELDS.items():

        old_value = previous_state.get(field)
        new_value = current_state.get(field)

        if old_value == new_value:
            continue

        if field == "status":

            if new_value == "resolved":
                event_type = "risk_resolved"

            elif old_value == "resolved":
                event_type = "risk_reopened"

        events.append(
            _create_event(
                db=db,
                finding=finding,
                event_type=event_type,
                summary=(
                    f"{field.replace('_', ' ').title()} changed "
                    f"from {old_value} to {new_value}."
                ),
                previous_state={
                    field: old_value,
                },
                new_state={
                    field: new_value,
                },
                evidence_snapshot=current_evidence_snapshot,
                source=source,
                actor_id=actor_id,
            )
        )

        # Detect evidence changes independently.
    previous_evidence_snapshot = (
        previous_evidence
        if previous_evidence is not None
        else []
    )

    if previous_evidence_snapshot != current_evidence_snapshot:

        events.append(
            _create_event(
                db=db,
                finding=finding,
                event_type="evidence_changed",
                summary="Supporting evidence changed.",
                previous_state={
                    "evidence_count": len(
                        previous_evidence_snapshot
                    ),
                },
                new_state={
                    "evidence_count": len(
                        current_evidence_snapshot
                    ),
                },
                evidence_snapshot={
                    "previous": previous_evidence_snapshot,
                    "current": current_evidence_snapshot,
                },
                source=source,
                actor_id=actor_id,
            )
        )
        

    return events