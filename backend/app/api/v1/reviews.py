from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_organization_role
from app.models.membership import OrganizationMembership
from app.schemas.review_request import (
    ReviewDecision,
    ReviewRequestCreate,
    ReviewRequestListResponse,
    ReviewRequestResponse,
)
from app.services.review_request_service import (
    ReviewRequestNotFoundError,
    ReviewRequestPermissionError,
    ReviewRequestValidationError,
    create_review_request,
    decide_review_request,
    get_review_request,
    list_review_requests,
)

router = APIRouter(prefix="/organizations", tags=["Human Review"])


def _raise_review_error(exc):
    if isinstance(exc, ReviewRequestNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ReviewRequestPermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ReviewRequestValidationError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise HTTPException(status_code=500, detail="Review request operation failed.")


@router.post(
    "/{organization_id}/reviews",
    response_model=ReviewRequestResponse,
    status_code=201,
)
def create_review(
    organization_id: UUID,
    request: ReviewRequestCreate,
    membership: OrganizationMembership = Depends(require_organization_role("owner", "admin", "member")),
    db: Session = Depends(get_db),
):
    try:
        return create_review_request(
            db,
            organization_id=organization_id,
            requested_by_user_id=membership.user_id,
            review_type=request.review_type,
            reason=request.reason,
            evidence_record_ids=request.evidence_record_ids,
            execution_id=request.execution_id,
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            proposed_interpretation=request.proposed_interpretation,
            assigned_to_user_id=request.assigned_to_user_id,
        )
    except (ReviewRequestNotFoundError, ReviewRequestPermissionError, ReviewRequestValidationError) as exc:
        db.rollback()
        _raise_review_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create review request.") from exc


@router.get("/{organization_id}/reviews", response_model=ReviewRequestListResponse)
def list_reviews(
    organization_id: UUID,
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected|clarification_requested|cancelled)$"),
    assigned_to_me: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    membership: OrganizationMembership = Depends(require_organization_role("owner", "admin", "member")),
    db: Session = Depends(get_db),
):
    items, total = list_review_requests(
        db,
        organization_id,
        status=status,
        assigned_to_user_id=membership.user_id if assigned_to_me else None,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return {"organization_id": organization_id, "total": total, "reviews": items}


@router.get("/{organization_id}/reviews/{review_id}", response_model=ReviewRequestResponse)
def get_review(
    organization_id: UUID,
    review_id: UUID,
    membership: OrganizationMembership = Depends(require_organization_role("owner", "admin", "member")),
    db: Session = Depends(get_db),
):
    try:
        return get_review_request(db, organization_id, review_id)
    except ReviewRequestNotFoundError as exc:
        _raise_review_error(exc)


@router.post(
    "/{organization_id}/reviews/{review_id}/decision",
    response_model=ReviewRequestResponse,
)
def decide_review(
    organization_id: UUID,
    review_id: UUID,
    request: ReviewDecision,
    membership: OrganizationMembership = Depends(require_organization_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    try:
        return decide_review_request(
            db,
            organization_id=organization_id,
            review_id=review_id,
            actor_user_id=membership.user_id,
            decision=request.decision,
            comment=request.comment,
        )
    except (ReviewRequestNotFoundError, ReviewRequestPermissionError, ReviewRequestValidationError) as exc:
        db.rollback()
        _raise_review_error(exc)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not record review decision.") from exc
