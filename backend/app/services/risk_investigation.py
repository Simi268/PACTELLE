from collections import Counter
import json

from app.services.risk_explanation import explain_risk_finding


STATE_EVENT_TYPES = {
    "severity_changed",
    "status_changed",
    "risk_resolved",
    "risk_reopened",
    "assessment_changed",
    "deadline_changed",
    "confidence_changed",
}


def _canonicalize(item):
    return json.dumps(
        item,
        sort_keys=True,
        default=str,
    )


def _compare_evidence(previous, current):
    """
    Identify evidence additions and removals using historical snapshots.
    Preserves duplicate evidence counts.
    """

    previous = previous or []
    current = current or []

    previous_map = {}
    current_map = {}

    for item in previous:
        key = _canonicalize(item)
        previous_map.setdefault(key, []).append(item)

    for item in current:
        key = _canonicalize(item)
        current_map.setdefault(key, []).append(item)

    previous_counts = Counter(
        _canonicalize(item) for item in previous
    )

    current_counts = Counter(
        _canonicalize(item) for item in current
    )

    added = []
    removed = []

    all_keys = previous_counts.keys() | current_counts.keys()

    for key in all_keys:

        difference = current_counts[key] - previous_counts[key]

        if difference > 0:
            added.extend(current_map[key][:difference])

        elif difference < 0:
            removed.extend(previous_map[key][:-difference])

    return {
        "added": added,
        "removed": removed,
        "previous_count": len(previous),
        "current_count": len(current),
    }


def reconstruct_investigation(finding, events):
    """
    Reconstruct the historical investigation of a risk finding.
    """

    timeline = []
    evidence_evolution = []
    assessment_evolution = []

    unresolved_questions = []

    events = sorted(
        events,
        key=lambda event: (
            event.created_at,
            str(event.id),
        ),
    )

    for event in events:

        timeline.append({
            "event_id": str(event.id),
            "event_type": event.event_type,
            "source": event.source,
            "actor_id": (
                str(event.actor_id)
                if event.actor_id else None
            ),
            "summary": event.summary,
            "created_at": event.created_at,
            "previous_state": event.previous_state,
            "new_state": event.new_state,
        })

        if event.event_type in STATE_EVENT_TYPES:
            assessment_evolution.append({
                "event_id": str(event.id),
                "event_type": event.event_type,
                "previous_state": event.previous_state,
                "new_state": event.new_state,
                "source": event.source,
                "created_at": event.created_at,
            })

        if event.event_type == "evidence_changed":

            snapshot = event.evidence_snapshot or {}

            previous = snapshot.get("previous", [])
            current = snapshot.get("current", [])

            comparison = _compare_evidence(
                previous,
                current,
            )

            evidence_evolution.append({
                "event_id": str(event.id),
                "created_at": event.created_at,
                "source": event.source,
                "summary": event.summary,
                **comparison,
            })

    # Reuse the existing explanation engine for current evidence.
    current_explanation = explain_risk_finding(finding)

    unresolved_questions.extend(
        current_explanation["uncertainties"]
    )

    if not events:
        unresolved_questions.append(
            "No historical risk events are available."
        )

    if not any(
        event.event_type == "evidence_changed"
        for event in events
    ):
        unresolved_questions.append(
            "No historical evidence-change snapshots are available."
        )

    if finding.assessment_status == "provisional":
        unresolved_questions.append(
            "The current risk assessment has not been confirmed."
        )

    unresolved_questions = list(
        dict.fromkeys(unresolved_questions)
    )

    return {
        "risk_finding_id": str(finding.id),

        "risk_overview": current_explanation["risk"],

        "investigation_summary": {
            "total_events": len(events),
            "first_recorded_at": (
                events[0].created_at if events else None
            ),
            "last_recorded_at": (
                events[-1].created_at if events else None
            ),
            "evidence_change_count": len(evidence_evolution),
            "assessment_change_count": len(assessment_evolution),
            "current_status": finding.status,
            "current_assessment": finding.assessment_status,
        },

        "timeline": timeline,

        "evidence_evolution": evidence_evolution,

        "assessment_evolution": assessment_evolution,

        "current_evidence": {
            "supporting": current_explanation["supporting_evidence"],
            "rejected": current_explanation["rejected_evidence"],
            "summary": current_explanation["evidence_summary"],
        },

        "unresolved_questions": unresolved_questions,

        "recommended_action": current_explanation["recommended_action"],

        "human_review_required": (
            current_explanation["human_review_required"]
            or bool(unresolved_questions)
        ),
    }