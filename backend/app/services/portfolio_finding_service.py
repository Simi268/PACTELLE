from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord

from app.models.portfolio_risk_finding import (
    PortfolioRiskFinding,
    PortfolioRiskFindingContract,
    PortfolioRiskFindingEvidence,
)


class PortfolioFindingError(Exception):
    pass


class PortfolioFindingValidationError(PortfolioFindingError):
    pass


class PortfolioFindingNotFoundError(PortfolioFindingError):
    pass


VALID_FINDING_TYPES = {
    "similarity",
    "potential_conflict",
    "repeated_risk",
    "exposure_concentration",
}

VALID_SEVERITIES = {
    "critical",
    "high",
    "medium",
    "low",
}

VALID_STATUSES = {
    "open",
    "acknowledged",
    "resolved",
}

VALID_ASSESSMENT_STATUSES = {
    "provisional",
    "confirmed",
}


def _validate_references(
    db: Session,
    organization_id: UUID,
    contract_ids: list[UUID],
    evidence_ids: list[UUID],
):
    contracts = db.scalars(
        select(Contract).where(
            Contract.id.in_(contract_ids),
            Contract.organization_id == organization_id,
        )
    ).all()

    if len(contracts) != len(set(contract_ids)):
        raise PortfolioFindingValidationError(
            "One or more contracts do not belong to this organization."
        )

    evidence_records = db.execute(
        select(
            EvidenceRecord.id,
            ContractDocument.contract_id,
        )
        .join(
            ContractDocument,
            EvidenceRecord.document_id == ContractDocument.id,
        )
        .join(
            Contract,
            ContractDocument.contract_id == Contract.id,
        )
        .where(
            EvidenceRecord.id.in_(evidence_ids),
            Contract.organization_id == organization_id,
        )
    ).all()

    if len(evidence_records) != len(set(evidence_ids)):
        raise PortfolioFindingValidationError(
            "One or more evidence records do not belong to this organization."
        )

    linked_contract_ids = {
        row.contract_id for row in evidence_records
    }

    if not linked_contract_ids.issubset(set(contract_ids)):
        raise PortfolioFindingValidationError(
            "Evidence references contracts not linked to this finding."
        )


def persist_portfolio_findings(
    db: Session,
    organization_id: UUID,
    generated_findings: list[dict],
    commit: bool = False,
) -> dict:
    """
    Persist generated portfolio findings.

    commit=False allows the caller to control the transaction.
    Duplicate active findings are reused rather than recreated.
    """

    created = []
    existing = []

    try:
        with db.begin_nested():

            organization = db.scalar(
                select(Organization)
                .where(Organization.id == organization_id)
                .with_for_update()
            )

            if organization is None:
                raise PortfolioFindingNotFoundError(
                    "Organization not found."
                )

            for candidate in generated_findings:

                finding_type = candidate.get("finding_type")
                severity = candidate.get("severity")
                assessment_status = candidate.get(
                    "assessment_status"
                )

                if finding_type not in VALID_FINDING_TYPES:
                    raise PortfolioFindingValidationError(
                        "Invalid finding type."
                    )

                if severity not in VALID_SEVERITIES:
                    raise PortfolioFindingValidationError(
                        "Invalid severity."
                    )

                if assessment_status not in VALID_ASSESSMENT_STATUSES:
                    raise PortfolioFindingValidationError(
                        "Invalid assessment status."
                    )

                rule_id = candidate.get("rule_id")

                if not rule_id:
                    raise PortfolioFindingValidationError(
                        "Finding rule_id is required."
                    )

                contract_ids = list(
                    dict.fromkeys(
                        UUID(str(item))
                        for item in candidate.get("contract_ids", [])
                    )
                )

                evidence_ids = list(
                    dict.fromkeys(
                        UUID(str(item))
                        for item in candidate.get("evidence_ids", [])
                    )
                )

                if len(contract_ids) < 2:
                    raise PortfolioFindingValidationError(
                        "Portfolio findings require at least two contracts."
                    )

                if len(evidence_ids) < 2:
                    raise PortfolioFindingValidationError(
                        "Portfolio findings require at least two evidence records."
                    )

                _validate_references(
                    db,
                    organization_id,
                    contract_ids,
                    evidence_ids,
                )

                duplicate = db.scalar(
                    select(PortfolioRiskFinding).where(
                        PortfolioRiskFinding.organization_id
                        == organization_id,
                        PortfolioRiskFinding.rule_id == rule_id,
                        PortfolioRiskFinding.status != "resolved",
                    )
                )

                if duplicate:
                    existing.append(duplicate)
                    continue

                finding = PortfolioRiskFinding(
                    organization_id=organization_id,
                    finding_type=finding_type,
                    title=candidate["title"],
                    description=candidate["description"],
                    severity=severity,
                    status="open",
                    assessment_status=assessment_status,
                    detection_method=candidate.get(
                        "detection_method",
                        "rule_based",
                    ),
                    rule_id=rule_id,
                    rule_version=candidate.get(
                        "rule_version",
                        "1.0",
                    ),
                    confidence=candidate.get("confidence"),
                    details=candidate.get("details"),
                )

                db.add(finding)
                db.flush()

                for contract_id in contract_ids:
                    db.add(
                        PortfolioRiskFindingContract(
                            portfolio_finding_id=finding.id,
                            contract_id=contract_id,
                        )
                    )

                for evidence_id in evidence_ids:
                    db.add(
                        PortfolioRiskFindingEvidence(
                            portfolio_finding_id=finding.id,
                            evidence_record_id=evidence_id,
                        )
                    )

                created.append(finding)

            db.flush()

        if commit:
            db.commit()

    except Exception:
        if commit:
            db.rollback()
        raise

    return {
        "created_count": len(created),
        "existing_count": len(existing),
        "created_findings": created,
        "existing_findings": existing,
    }


def update_portfolio_finding_status(
    db: Session,
    organization_id: UUID,
    finding_id: UUID,
    new_status: str,
    commit: bool = False,
) -> PortfolioRiskFinding:
    """
    Update a portfolio finding's lifecycle status.

    Supported transitions:
        open -> acknowledged
        open -> resolved
        acknowledged -> resolved
        acknowledged -> open
        resolved -> open
    """

    allowed_transitions = {
        "open": {"acknowledged", "resolved"},
        "acknowledged": {"resolved", "open"},
        "resolved": {"open"},
    }

    if new_status not in VALID_STATUSES:
        raise PortfolioFindingValidationError(
            "Invalid finding status."
        )

    try:
        with db.begin_nested():

            finding = db.scalar(
                select(PortfolioRiskFinding)
                .where(
                    PortfolioRiskFinding.id == finding_id,
                    PortfolioRiskFinding.organization_id
                    == organization_id,
                )
                .with_for_update()
            )

            if finding is None:
                raise PortfolioFindingNotFoundError(
                    "Portfolio finding not found."
                )


            if new_status not in allowed_transitions[finding.status]:
                raise PortfolioFindingValidationError(
                    f"Cannot transition from {finding.status} "
                    f"to {new_status}."
                )

            finding.status = new_status

            db.flush()

        if commit:
            db.commit()

        return finding

    except Exception:
        if commit:
            db.rollback()
        raise