from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_organization_role
from app.models.membership import OrganizationMembership
from app.schemas.portfolio_action import (
    PortfolioActionCreate,
    PortfolioActionAssignmentUpdate,
    PortfolioActionStatusUpdate,
    PortfolioActionResponse,
    PortfolioActionListResponse,
    PortfolioActionRecommendationResponse,
)
from app.services.portfolio_action_service import (
    PortfolioActionNotFoundError,
    PortfolioActionValidationError,
    create_portfolio_action,
    generate_actions_for_finding,
    get_portfolio_action,
    list_portfolio_actions,
    transition_portfolio_action,
    update_portfolio_action_assignment,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Portfolio Actions"],
)


def _http_error(exc):
    if isinstance(exc, PortfolioActionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PortfolioActionValidationError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise HTTPException(status_code=500, detail="Portfolio action operation failed.")


@router.post(
    "/{organization_id}/portfolio-findings/{finding_id}/action-recommendations",
    response_model=PortfolioActionRecommendationResponse,
)
def create_recommendations(
    organization_id: UUID,
    finding_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    try:
        result = generate_actions_for_finding(
            db, organization_id, finding_id, membership.user_id, commit=True
        )
        actions = result["created_actions"] + result["existing_actions"]
        return {
            "organization_id": organization_id,
            "finding_id": finding_id,
            "created_count": result["created_count"],
            "existing_count": result["existing_count"],
            "actions": actions,
        }
    except (PortfolioActionNotFoundError, PortfolioActionValidationError) as exc:
        _http_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not generate action recommendations.")


@router.post(
    "/{organization_id}/portfolio-actions",
    response_model=PortfolioActionResponse,
    status_code=201,
)
def create_action(
    organization_id: UUID,
    request: PortfolioActionCreate,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    try:
        return create_portfolio_action(
            db,
            organization_id,
            request.finding_id,
            membership.user_id,
            title=request.title,
            description=request.description,
            rationale=request.rationale,
            priority=request.priority,
            due_date=request.due_date,
            assigned_to_user_id=request.assigned_to_user_id,
            commit=True,
        )
    except (PortfolioActionNotFoundError, PortfolioActionValidationError) as exc:
        _http_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not create portfolio action.")


@router.get(
    "/{organization_id}/portfolio-actions",
    response_model=PortfolioActionListResponse,
)
def list_actions(
    organization_id: UUID,
    finding_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    try:
        actions, total = list_portfolio_actions(
            db,
            organization_id,
            finding_id=finding_id,
            status=status,
            priority=priority,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return {
            "organization_id": organization_id,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
            "actions": actions,
        }
    except PortfolioActionValidationError as exc:
        _http_error(exc)


@router.get(
    "/{organization_id}/portfolio-actions/{action_id}",
    response_model=PortfolioActionResponse,
)
def get_action(
    organization_id: UUID,
    action_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_portfolio_action(db, organization_id, action_id)
    except PortfolioActionNotFoundError as exc:
        _http_error(exc)


@router.patch(
    "/{organization_id}/portfolio-actions/{action_id}/assignment",
    response_model=PortfolioActionResponse,
)
def update_assignment(
    organization_id: UUID,
    action_id: UUID,
    request: PortfolioActionAssignmentUpdate,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    try:
        update_portfolio_action_assignment(
            db,
            organization_id,
            action_id,
            membership.user_id,
            request.assigned_to_user_id,
            commit=True,
        )
        return get_portfolio_action(db, organization_id, action_id)
    except (PortfolioActionNotFoundError, PortfolioActionValidationError) as exc:
        _http_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not update action assignment.")


@router.patch(
    "/{organization_id}/portfolio-actions/{action_id}/status",
    response_model=PortfolioActionResponse,
)
def update_action_status(
    organization_id: UUID,
    action_id: UUID,
    request: PortfolioActionStatusUpdate,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    try:
        transition_portfolio_action(
            db,
            organization_id,
            action_id,
            membership.user_id,
            request.status,
            comment=request.comment,
            commit=True,
        )
        return get_portfolio_action(db, organization_id, action_id)
    except (PortfolioActionNotFoundError, PortfolioActionValidationError) as exc:
        _http_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not update action status.")
