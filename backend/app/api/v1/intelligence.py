from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_organization_role

from app.models.organization import Organization
from app.models.membership import OrganizationMembership
from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.risk_finding import RiskFinding


router = APIRouter(
    prefix="/organizations",
    tags=["Organization Intelligence"],
)


def _verify_organization(
    organization_id: UUID,
    db: Session,
):
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Organization not found.",
        )

    return organization


def _grouped_counts(db, model, column, *filters):
    rows = (
        db.query(column, func.count(model.id))
        .filter(*filters)
        .group_by(column)
        .all()
    )

    return {
        key: count
        for key, count in rows
    }


# =========================================================
# 1. ORGANIZATION DASHBOARD
# =========================================================

@router.get("/{organization_id}/dashboard")
def organization_dashboard(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    _verify_organization(organization_id, db)

    today = date.today()

    total_contracts = (
        db.query(func.count(Contract.id))
        .filter(
            Contract.organization_id == organization_id
        )
        .scalar()
    ) or 0

    contract_status_counts = _grouped_counts(
        db,
        Contract,
        Contract.status,
        Contract.organization_id == organization_id,
    )

    total_documents = (
        db.query(func.count(ContractDocument.id))
        .join(
            Contract,
            Contract.id == ContractDocument.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id
        )
        .scalar()
    ) or 0

    document_status_counts = (
        db.query(
            ContractDocument.processing_status,
            func.count(ContractDocument.id),
        )
        .join(
            Contract,
            Contract.id == ContractDocument.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id
        )
        .group_by(ContractDocument.processing_status)
        .all()
    )

    document_status_counts = {
        status: count
        for status, count in document_status_counts
    }

    open_risk_filters = (
        RiskFinding.status != "resolved",
        RiskFinding.contract_id == Contract.id,
        Contract.organization_id == organization_id,
    )

    open_risks = (
        db.query(func.count(RiskFinding.id))
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(*open_risk_filters)
        .scalar()
    ) or 0

    risk_severity_counts = (
        db.query(
            RiskFinding.severity,
            func.count(RiskFinding.id),
        )
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            RiskFinding.status != "resolved",
            Contract.organization_id == organization_id,
        )
        .group_by(RiskFinding.severity)
        .all()
    )

    risk_severity_counts = {
        severity: count
        for severity, count in risk_severity_counts
    }

    upcoming_renewals = (
        db.query(func.count(RiskFinding.id))
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
            RiskFinding.rule_id == "RENEWAL-001",
            RiskFinding.status != "resolved",
            RiskFinding.deadline_date >= today,
            RiskFinding.deadline_date <= today + timedelta(days=90),
        )
        .scalar()
    ) or 0

    expiring_contracts = (
        db.query(func.count(Contract.id))
        .filter(
            Contract.organization_id == organization_id,
            Contract.expiration_date >= today,
            Contract.expiration_date <= today + timedelta(days=30),
            Contract.status.notin_(["expired", "terminated"]),
        )
        .scalar()
    ) or 0

    return {
        "organization_id": str(organization_id),
        "generated_at": today.isoformat(),

        "contracts": {
            "total": total_contracts,
            "by_status": contract_status_counts,
        },

        "documents": {
            "total": total_documents,
            "by_processing_status": document_status_counts,
        },

        "risks": {
            "total_open": open_risks,
            "by_severity": risk_severity_counts,
        },

        "monitoring": {
            "upcoming_renewals_next_90_days": upcoming_renewals,
            "contracts_expiring_next_30_days": expiring_contracts,
        },
    }


# =========================================================
# 2. UPCOMING RENEWALS
# =========================================================

@router.get("/{organization_id}/upcoming-renewals")
def get_upcoming_renewals(
    organization_id: UUID,
    days: int = Query(default=90, ge=1, le=365),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    _verify_organization(organization_id, db)

    today = date.today()
    deadline_limit = today + timedelta(days=days)

    results = (
        db.query(RiskFinding, Contract)
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
            RiskFinding.rule_id == "RENEWAL-001",
            RiskFinding.status != "resolved",
            RiskFinding.deadline_date >= today,
            RiskFinding.deadline_date <= deadline_limit,
        )
        .order_by(RiskFinding.deadline_date.asc())
        .all()
    )

    renewals = []

    for finding, contract in results:
        renewals.append({
            "risk_finding_id": str(finding.id),
            "contract_id": str(contract.id),
            "contract_title": contract.title,
            "contract_expiration_date": (
                contract.expiration_date.isoformat()
                if contract.expiration_date
                else None
            ),
            "non_renewal_deadline": (
                finding.deadline_date.isoformat()
                if finding.deadline_date
                else None
            ),
            "days_until_deadline": (
                finding.deadline_date - today
            ).days,
            "severity": finding.severity,
            "assessment_status": finding.assessment_status,
            "risk_status": finding.status,
        })

    return {
        "organization_id": str(organization_id),
        "period_days": days,
        "total": len(renewals),
        "renewals": renewals,
    }


# =========================================================
# 3. EXPIRING CONTRACTS
# =========================================================

@router.get("/{organization_id}/expiring-contracts")
def get_expiring_contracts(
    organization_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    _verify_organization(organization_id, db)

    today = date.today()
    expiration_limit = today + timedelta(days=days)

    contracts = (
        db.query(Contract)
        .filter(
            Contract.organization_id == organization_id,
            Contract.expiration_date >= today,
            Contract.expiration_date <= expiration_limit,
            Contract.status.notin_(["expired", "terminated"]),
        )
        .order_by(Contract.expiration_date.asc())
        .all()
    )

    results = []

    for contract in contracts:
        results.append({
            "contract_id": str(contract.id),
            "title": contract.title,
            "contract_type": contract.contract_type,
            "status": contract.status,
            "effective_date": (
                contract.effective_date.isoformat()
                if contract.effective_date
                else None
            ),
            "expiration_date": contract.expiration_date.isoformat(),
            "days_until_expiration": (
                contract.expiration_date - today
            ).days,
        })

    return {
        "organization_id": str(organization_id),
        "period_days": days,
        "total": len(results),
        "contracts": results,
    }


# =========================================================
# 4. RISK OVERVIEW
# =========================================================

@router.get("/{organization_id}/risk-overview")
def get_risk_overview(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    _verify_organization(organization_id, db)

    base_query = (
        db.query(RiskFinding)
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
        )
    )

    total_findings = base_query.count()

    open_findings = base_query.filter(
        RiskFinding.status != "resolved"
    ).count()

    resolved_findings = base_query.filter(
        RiskFinding.status == "resolved"
    ).count()

    severity_counts = (
        db.query(
            RiskFinding.severity,
            func.count(RiskFinding.id),
        )
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
            RiskFinding.status != "resolved",
        )
        .group_by(RiskFinding.severity)
        .all()
    )

    assessment_counts = (
        db.query(
            RiskFinding.assessment_status,
            func.count(RiskFinding.id),
        )
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
            RiskFinding.status != "resolved",
        )
        .group_by(RiskFinding.assessment_status)
        .all()
    )

    risk_type_counts = (
        db.query(
            RiskFinding.risk_type,
            func.count(RiskFinding.id),
        )
        .join(
            Contract,
            Contract.id == RiskFinding.contract_id,
        )
        .filter(
            Contract.organization_id == organization_id,
            RiskFinding.status != "resolved",
        )
        .group_by(RiskFinding.risk_type)
        .all()
    )

    return {
        "organization_id": str(organization_id),

        "summary": {
            "total_findings": total_findings,
            "open_findings": open_findings,
            "resolved_findings": resolved_findings,
        },

        "open_findings_by_severity": {
            severity: count
            for severity, count in severity_counts
        },

        "open_findings_by_assessment": {
            assessment: count
            for assessment, count in assessment_counts
        },

        "open_findings_by_type": {
            risk_type: count
            for risk_type, count in risk_type_counts
        },
    }