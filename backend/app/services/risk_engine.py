from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence

from app.services.evidence_extractor import extract_number


RENEWAL_RULE_ID = "RENEWAL-001"
RENEWAL_RULE_VERSION = "1.0"


def detect_automatic_renewal_risk(
    db: Session,
    contract_id,
):
    """
    Detect automatic renewal exposure using extracted
    contractual evidence with source provenance.

    Creates a risk finding, calculates the non-renewal deadline,
    links supporting evidence, and tracks evidence verification.

    Assessment status:
    - provisional: at least one supporting evidence record is unverified
    - confirmed: all selected supporting evidence records are verified

    Rejected evidence is never used.
    """

    # --------------------------------------------------
    # 1. FETCH CONTRACT
    # --------------------------------------------------

    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id)
        .first()
    )

    if not contract:
        raise ValueError("Contract not found.")

    if not contract.expiration_date:
        return {
            "status": "skipped",
            "reason": "Contract expiration date is missing."
        }

    # --------------------------------------------------
    # 2. FETCH CONTRACT DOCUMENTS
    # --------------------------------------------------

    documents = (
        db.query(ContractDocument)
        .filter(
            ContractDocument.contract_id == contract_id
        )
        .all()
    )

    document_ids = [
        document.id for document in documents
    ]

    if not document_ids:
        return {
            "status": "skipped",
            "reason": "No contract documents found."
        }

    # --------------------------------------------------
    # 3. FETCH VALID RENEWAL EVIDENCE
    # --------------------------------------------------

    evidence_records = (
        db.query(EvidenceRecord)
        .filter(
            EvidenceRecord.document_id.in_(document_ids),
            EvidenceRecord.evidence_type.in_([
                "renewal_period",
                "renewal_notice"
            ]),
            EvidenceRecord.verification_status != "rejected"
        )
        .all()
    )

    renewal_period_records = [
        record
        for record in evidence_records
        if record.evidence_type == "renewal_period"
    ]

    renewal_notice_records = [
        record
        for record in evidence_records
        if record.evidence_type == "renewal_notice"
    ]

    if not renewal_period_records or not renewal_notice_records:
        return {
            "status": "skipped",
            "reason": "Required renewal evidence is incomplete."
        }

    # Prefer verified evidence when multiple records exist.
    renewal_period_records.sort(
        key=lambda record: (
            record.verification_status != "verified"
        )
    )

    renewal_notice_records.sort(
        key=lambda record: (
            record.verification_status != "verified"
        )
    )

    renewal_period = renewal_period_records[0]
    renewal_notice = renewal_notice_records[0]

    supporting_evidence = [
        renewal_period,
        renewal_notice
    ]

    # --------------------------------------------------
    # 4. DETERMINE ASSESSMENT STATUS
    # --------------------------------------------------

    assessment_status = (
        "confirmed"
        if all(
            evidence.verification_status == "verified"
            for evidence in supporting_evidence
        )
        else "provisional"
    )

    # --------------------------------------------------
    # 5. EXTRACT NOTICE PERIOD
    # --------------------------------------------------

    notice_days = extract_number(
        renewal_notice.evidence_text,
        "days"
    )

    if notice_days is None:
        return {
            "status": "skipped",
            "reason": "Could not determine the notice period."
        }

    # --------------------------------------------------
    # 6. CALCULATE NON-RENEWAL DEADLINE
    # --------------------------------------------------

    non_renewal_deadline = (
        contract.expiration_date - timedelta(days=notice_days)
    )

    # --------------------------------------------------
    # 7. CHECK FOR EXISTING RISK FINDING
    # --------------------------------------------------

    existing_finding = (
        db.query(RiskFinding)
        .filter(
            RiskFinding.contract_id == contract_id,
            RiskFinding.rule_id == RENEWAL_RULE_ID,
            RiskFinding.status != "resolved"
        )
        .first()
    )

    if existing_finding:

        # Synchronize assessment status with current evidence.
        existing_finding.assessment_status = assessment_status

        # Update the calculated deadline.
        existing_finding.deadline_date = non_renewal_deadline

        # Add missing supporting evidence links.
        for evidence in supporting_evidence:

            existing_link = (
                db.query(RiskFindingEvidence)
                .filter(
                    RiskFindingEvidence.risk_finding_id
                    == existing_finding.id,
                    RiskFindingEvidence.evidence_record_id
                    == evidence.id
                )
                .first()
            )

            if not existing_link:
                db.add(
                    RiskFindingEvidence(
                        risk_finding_id=existing_finding.id,
                        evidence_record_id=evidence.id
                    )
                )

        db.commit()
        db.refresh(existing_finding)

        return {
            "status": "already_exists",
            "risk_finding_id": str(existing_finding.id),
            "risk_type": existing_finding.risk_type,
            "severity": existing_finding.severity,
            "assessment_status": existing_finding.assessment_status,
            "deadline_date": (
                existing_finding.deadline_date.isoformat()
                if existing_finding.deadline_date
                else None
            )
        }

    # --------------------------------------------------
    # 8. CREATE NEW RISK FINDING
    # --------------------------------------------------

    finding = RiskFinding(
        contract_id=contract_id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description=(
            "This contract contains automatic renewal provisions. "
            f"Non-renewal requires at least {notice_days} days' "
            "advance notice. The calculated notice deadline is "
            f"{non_renewal_deadline.isoformat()}."
        ),
        severity="medium",
        status="open",
        assessment_status=assessment_status,
        detection_method="rule_based",
        rule_id=RENEWAL_RULE_ID,
        rule_version=RENEWAL_RULE_VERSION,
        confidence=None,
        deadline_date=non_renewal_deadline
    )

    db.add(finding)
    db.flush()

    # --------------------------------------------------
    # 9. LINK SUPPORTING EVIDENCE
    # --------------------------------------------------

    for evidence in supporting_evidence:

        db.add(
            RiskFindingEvidence(
                risk_finding_id=finding.id,
                evidence_record_id=evidence.id
            )
        )

    # --------------------------------------------------
    # 10. SAVE RISK FINDING
    # --------------------------------------------------

    db.commit()
    db.refresh(finding)

    # --------------------------------------------------
    # 11. RETURN RESULT
    # --------------------------------------------------

    return {
        "status": "created",
        "risk_finding_id": str(finding.id),
        "risk_type": finding.risk_type,
        "severity": finding.severity,
        "assessment_status": finding.assessment_status,
        "notice_period_days": notice_days,
        "deadline_date": finding.deadline_date.isoformat(),
        "contract_expiration_date": (
            contract.expiration_date.isoformat()
        ),
        "non_renewal_deadline": (
            non_renewal_deadline.isoformat()
        ),
        "supporting_evidence_count": len(supporting_evidence)
    }