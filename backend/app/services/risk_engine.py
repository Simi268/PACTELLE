from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence

from app.services.evidence_extractor import extract_number
from app.services.risk_event_service import (
    build_risk_snapshot,
    build_evidence_snapshot,
    record_risk_changes,
)


RENEWAL_RULE_ID = "RENEWAL-001"
RENEWAL_RULE_VERSION = "1.0"

_UNSET = object()


def _get_active_finding(db: Session, contract_id):
    return (
        db.query(RiskFinding)
        .filter(
            RiskFinding.contract_id == contract_id,
            RiskFinding.rule_id == RENEWAL_RULE_ID,
            RiskFinding.status != "resolved",
        )
        .first()
    )


def capture_risk_history_context(db: Session, contract_id):
    """
    Capture the existing finding and its linked evidence before
    document reprocessing can replace or delete evidence records.
    """
    finding = _get_active_finding(db, contract_id)

    if finding is None:
        return None, []

    previous_state = build_risk_snapshot(finding)

    previous_evidence_records = (
        db.query(EvidenceRecord)
        .join(
            RiskFindingEvidence,
            RiskFindingEvidence.evidence_record_id == EvidenceRecord.id,
        )
        .filter(
            RiskFindingEvidence.risk_finding_id == finding.id
        )
        .all()
    )

    previous_evidence = build_evidence_snapshot(
        previous_evidence_records
    )

    return previous_state, previous_evidence


def _sync_evidence_links(db, finding, supporting_evidence):
    valid_ids = {
        evidence.id
        for evidence in supporting_evidence
    }

    existing_links = (
        db.query(RiskFindingEvidence)
        .filter(
            RiskFindingEvidence.risk_finding_id == finding.id
        )
        .all()
    )

    for link in existing_links:
        if link.evidence_record_id not in valid_ids:
            db.delete(link)

    existing_ids = {
        link.evidence_record_id
        for link in existing_links
        if link.evidence_record_id in valid_ids
    }

    for evidence in supporting_evidence:
        if evidence.id not in existing_ids:
            db.add(
                RiskFindingEvidence(
                    risk_finding_id=finding.id,
                    evidence_record_id=evidence.id,
                )
            )

    db.flush()


def _reconcile_incomplete_finding(
    db,
    finding,
    reason,
    commit=True,
    previous_state=None,
    previous_evidence=None,
    source="system",
):
    if finding is None:
        return {
            "status": "skipped",
            "reason": reason,
        }

    finding.assessment_status = "provisional"

    _sync_evidence_links(
        db,
        finding,
        supporting_evidence=[],
    )

    record_risk_changes(
        db,
        finding,
        previous_state=previous_state,
        previous_evidence=previous_evidence or [],
        current_evidence=[],
        source=source,
    )

    if commit:
        db.commit()
        db.refresh(finding)

    return {
        "status": "reconciled",
        "risk_finding_id": str(finding.id),
        "assessment_status": "provisional",
        "reason": reason,
    }


def detect_automatic_renewal_risk(
    db: Session,
    contract_id,
    commit=True,
    previous_state=_UNSET,
    previous_evidence=_UNSET,
    source="system",
):
    """
    Detect automatic renewal exposure and record every meaningful
    change in the same transaction.

    previous_state / previous_evidence can be supplied by the document
    pipeline when evidence is about to be replaced.
    """

    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id)
        .first()
    )

    if contract is None:
        raise ValueError("Contract not found.")

    existing_finding = _get_active_finding(db, contract_id)

    # Direct callers capture the current state themselves.
    # The pipeline supplies a pre-reprocessing snapshot instead.
    if previous_state is _UNSET:
        if existing_finding is not None:
            previous_state = build_risk_snapshot(existing_finding)

            old_records = (
                db.query(EvidenceRecord)
                .join(
                    RiskFindingEvidence,
                    RiskFindingEvidence.evidence_record_id
                    == EvidenceRecord.id,
                )
                .filter(
                    RiskFindingEvidence.risk_finding_id
                    == existing_finding.id
                )
                .all()
            )
            previous_evidence = build_evidence_snapshot(old_records)
        else:
            previous_state = None
            previous_evidence = []

    elif previous_evidence is _UNSET:
        previous_evidence = []

    def reconcile(reason):
        return _reconcile_incomplete_finding(
            db,
            existing_finding,
            reason,
            commit=commit,
            previous_state=previous_state,
            previous_evidence=previous_evidence,
            source=source,
        )

    if not contract.expiration_date:
        return reconcile("Contract expiration date is missing.")

    documents = (
        db.query(ContractDocument)
        .filter(ContractDocument.contract_id == contract_id)
        .all()
    )

    document_ids = [document.id for document in documents]

    if not document_ids:
        return reconcile("No contract documents found.")

    evidence_records = (
        db.query(EvidenceRecord)
        .filter(
            EvidenceRecord.document_id.in_(document_ids),
            EvidenceRecord.evidence_type.in_([
                "renewal_period",
                "renewal_notice",
            ]),
            EvidenceRecord.verification_status != "rejected",
        )
        .all()
    )

    renewal_period_records = [
        record for record in evidence_records
        if record.evidence_type == "renewal_period"
    ]

    renewal_notice_records = [
        record for record in evidence_records
        if record.evidence_type == "renewal_notice"
    ]

    if not renewal_period_records or not renewal_notice_records:
        return reconcile("Required renewal evidence is incomplete.")

    renewal_period_records.sort(
        key=lambda record: record.verification_status != "verified"
    )
    renewal_notice_records.sort(
        key=lambda record: record.verification_status != "verified"
    )

    supporting_evidence = [
        renewal_period_records[0],
        renewal_notice_records[0],
    ]

    assessment_status = (
        "confirmed"
        if all(
            record.verification_status == "verified"
            for record in supporting_evidence
        )
        else "provisional"
    )

    notice_days = extract_number(
        supporting_evidence[1].evidence_text,
        "days",
    )

    if notice_days is None:
        return reconcile("Could not determine the notice period.")

    deadline = contract.expiration_date - timedelta(days=notice_days)

    if existing_finding:
        existing_finding.assessment_status = assessment_status
        existing_finding.deadline_date = deadline

        _sync_evidence_links(
            db,
            existing_finding,
            supporting_evidence,
        )

        record_risk_changes(
            db,
            existing_finding,
            previous_state=previous_state,
            previous_evidence=previous_evidence,
            current_evidence=supporting_evidence,
            source=source,
        )

        if commit:
            db.commit()
            db.refresh(existing_finding)

        return {
            "status": "already_exists",
            "risk_finding_id": str(existing_finding.id),
            "risk_type": existing_finding.risk_type,
            "severity": existing_finding.severity,
            "assessment_status": existing_finding.assessment_status,
            "deadline_date": deadline.isoformat(),
        }

    finding = RiskFinding(
        contract_id=contract_id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description=(
            "This contract contains automatic renewal provisions. "
            f"Non-renewal requires at least {notice_days} days' "
            "advance notice. The calculated notice deadline is "
            f"{deadline.isoformat()}."
        ),
        severity="medium",
        status="open",
        assessment_status=assessment_status,
        detection_method="rule_based",
        rule_id=RENEWAL_RULE_ID,
        rule_version=RENEWAL_RULE_VERSION,
        confidence=None,
        deadline_date=deadline,
    )

    db.add(finding)
    db.flush()

    _sync_evidence_links(
        db,
        finding,
        supporting_evidence,
    )

    record_risk_changes(
        db,
        finding,
        previous_state=None,
        previous_evidence=[],
        current_evidence=supporting_evidence,
        source=source,
    )

    if commit:
        db.commit()
        db.refresh(finding)

    return {
        "status": "created",
        "risk_finding_id": str(finding.id),
        "risk_type": finding.risk_type,
        "severity": finding.severity,
        "assessment_status": finding.assessment_status,
        "notice_period_days": notice_days,
        "deadline_date": deadline.isoformat(),
        "contract_expiration_date": contract.expiration_date.isoformat(),
        "non_renewal_deadline": deadline.isoformat(),
        "supporting_evidence_count": len(supporting_evidence),
    }
