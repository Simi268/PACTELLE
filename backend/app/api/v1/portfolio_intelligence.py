from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.database import get_db
from app.core.dependencies import require_organization_role

from app.models.membership import OrganizationMembership
from app.models.portfolio_risk_finding import (
    PortfolioRiskFinding,
    PortfolioRiskFindingContract,
    PortfolioRiskFindingEvidence,
)
from app.models.evidence_record import EvidenceRecord
from app.models.document import ContractDocument

from app.schemas.portfolio_finding import (
    PortfolioFindingListResponse,
    PortfolioFindingResponse,
    PortfolioFindingStatusUpdate,
)

from app.services.portfolio_finding_service import (
    PortfolioFindingValidationError,
    PortfolioFindingNotFoundError,
    update_portfolio_finding_status,
)
from sqlalchemy.exc import SQLAlchemyError


router = APIRouter(
    prefix="/organizations",
    tags=["Portfolio Intelligence"],
)


def _finding_query(db: Session, organization_id: UUID):
    return (
        db.query(PortfolioRiskFinding)
        .filter(
            PortfolioRiskFinding.organization_id == organization_id
        )
        .options(
            selectinload(
                PortfolioRiskFinding.contract_links
            ).joinedload(
                PortfolioRiskFindingContract.contract
            ),
            selectinload(
                PortfolioRiskFinding.evidence_links
            ).joinedload(
                PortfolioRiskFindingEvidence.evidence_record
            ).joinedload(
                EvidenceRecord.document
            ).joinedload(
                ContractDocument.contract
            ),
        )
    )


def _serialize_finding(finding):
    contracts = []

    for link in finding.contract_links:
        contract = link.contract

        if contract is None:
            continue

        contracts.append({
            "id": contract.id,
            "title": contract.title,
            "status": contract.status,
        })

    evidence = []

    for link in finding.evidence_links:
        record = link.evidence_record

        if record is None:
            continue

        document = record.document
        contract = document.contract if document else None

        evidence.append({
            "evidence_id": record.id,
            "contract_id": contract.id if contract else None,
            "contract_title": contract.title if contract else None,
            "evidence_type": record.evidence_type,
            "claim": record.claim,
            "evidence_text": record.evidence_text,
            "verification_status": record.verification_status,
            "confidence": record.confidence,
            "page_number": record.page_number,
            "clause_id": record.clause_id,
            "document_id": record.document_id,
        })

    return {
        "id": finding.id,
        "organization_id": finding.organization_id,
        "finding_type": finding.finding_type,
        "title": finding.title,
        "description": finding.description,
        "severity": finding.severity,
        "status": finding.status,
        "assessment_status": finding.assessment_status,
        "detection_method": finding.detection_method,
        "rule_id": finding.rule_id,
        "rule_version": finding.rule_version,
        "confidence": finding.confidence,
        "details": finding.details,
        "created_at": finding.created_at,
        "contracts": contracts,
        "evidence": evidence,
    }


# =========================================================
# LIST PORTFOLIO FINDINGS
# =========================================================

@router.get(
    "/{organization_id}/portfolio-findings",
    response_model=PortfolioFindingListResponse,
)
def list_portfolio_findings(
    organization_id: UUID,

    finding_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),

    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),

    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),

    db: Session = Depends(get_db),
):
    valid_types = {
        "similarity",
        "potential_conflict",
        "repeated_risk",
        "exposure_concentration",
    }

    valid_severities = {"critical", "high", "medium", "low"}
    valid_statuses = {"open", "acknowledged", "resolved"}

    if finding_type is not None and finding_type not in valid_types:
        raise HTTPException(422, "Invalid finding type.")

    if severity is not None and severity not in valid_severities:
        raise HTTPException(422, "Invalid severity.")

    if status is not None and status not in valid_statuses:
        raise HTTPException(422, "Invalid finding status.")

    query = _finding_query(db, organization_id)

    if finding_type:
        query = query.filter(
            PortfolioRiskFinding.finding_type == finding_type
        )

    if severity:
        query = query.filter(
            PortfolioRiskFinding.severity == severity
        )

    if status:
        query = query.filter(
            PortfolioRiskFinding.status == status
        )

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    findings = (
        query
        .order_by(
            PortfolioRiskFinding.created_at.desc(),
            PortfolioRiskFinding.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "organization_id": organization_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "findings": [
            _serialize_finding(finding)
            for finding in findings
        ],
    }


# =========================================================
# GET PORTFOLIO FINDING
# =========================================================

@router.get(
    "/{organization_id}/portfolio-findings/{finding_id}",
    response_model=PortfolioFindingResponse,
)
def get_portfolio_finding(
    organization_id: UUID,
    finding_id: UUID,

    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),

    db: Session = Depends(get_db),
):
    finding = (
        _finding_query(db, organization_id)
        .filter(PortfolioRiskFinding.id == finding_id)
        .first()
    )

    if finding is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio finding not found.",
        )

    return _serialize_finding(finding)


# =========================================================
# HUMAN REVIEW / STATUS UPDATE
# =========================================================

@router.patch(
    "/{organization_id}/portfolio-findings/{finding_id}/status",
    response_model=PortfolioFindingResponse,
)
def update_portfolio_finding(
    organization_id: UUID,
    finding_id: UUID,
    request: PortfolioFindingStatusUpdate,

    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),

    db: Session = Depends(get_db),
):
    try:
        update_portfolio_finding_status(
            db=db,
            organization_id=organization_id,
            finding_id=finding_id,
            new_status=request.status,
            commit=True,
        )

    except PortfolioFindingNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Portfolio finding not found.",
        )

    except PortfolioFindingValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    finding = (
        _finding_query(db, organization_id)
        .filter(PortfolioRiskFinding.id == finding_id)
        .first()
    )

    return _serialize_finding(finding)

from app.schemas.portfolio_finding import (
    PortfolioFindingListResponse,
    PortfolioFindingResponse,
    PortfolioFindingStatusUpdate,
    PortfolioAnalysisResponse,
)

from app.services.portfolio_analysis_service import (
    run_organization_portfolio_analysis,
)
# =========================================================
# ORGANIZATION PORTFOLIO ANALYSIS
# =========================================================

@router.post(
    "/{organization_id}/portfolio-analysis",
    response_model=PortfolioAnalysisResponse,
)
def analyze_portfolio(
    organization_id: UUID,

    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),

    db: Session = Depends(get_db),
):
    """
    Execute complete organization-level portfolio analysis.

    Pipeline:
        1. Retrieve eligible obligations.
        2. Analyze cross-contract relationships.
        3. Generate potential risk findings.
        4. Persist findings with duplicate protection.
        5. Return findings requiring human review.

    Only organization owners and administrators can
    trigger portfolio analysis.
    """

    try:
        result = run_organization_portfolio_analysis(
            db=db,
            organization_id=organization_id,
            commit=True,
        )

        finding_ids = [
            finding.id
            for finding in (
                result["created_findings"]
                + result["existing_findings"]
            )
        ]

        findings = []

        if finding_ids:
            persisted_findings = (
                _finding_query(db, organization_id)
                .filter(
                    PortfolioRiskFinding.id.in_(finding_ids)
                )
                .all()
            )

            findings = [
                _serialize_finding(finding)
                for finding in persisted_findings
            ]

        return {
            "organization_id": organization_id,
            "status": "completed",

            "summary": {
                "retrieval": result["retrieval"],
                "intelligence": result["intelligence"],
                "generation": result["generation"],
                "persistence": result["persistence"],
            },

            "findings": findings,

            "human_review_queue": result[
                "human_review_queue"
            ],
        }

    except PortfolioFindingValidationError as exc:
        db.rollback()

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Portfolio analysis could not be completed.",
        )