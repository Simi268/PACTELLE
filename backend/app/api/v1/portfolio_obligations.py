from math import ceil
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_organization_role
from app.models.membership import OrganizationMembership
from app.schemas.contractual_obligation import (
    ObligationSyncResponse,
    ObligationUpdate,
    ContractualObligationResponse,
    ContractualObligationListResponse,
)
from app.services.obligation_lifecycle_service import (
    ObligationNotFoundError,
    ObligationValidationError,
    get_organization_obligation,
    list_organization_obligations,
    sync_organization_obligations,
    update_organization_obligation,
)

router = APIRouter(prefix="/organizations", tags=["Portfolio Obligations"])


def _serialize(record):
    return {
        "id": record.id,
        "organization_id": record.organization_id,
        "contract_id": record.contract_id,
        "evidence_record_id": record.evidence_record_id,
        "obligation_type": record.obligation_type,
        "obligation_family": record.obligation_family,
        "description": record.description,
        "claim": record.claim,
        "original_text": record.original_text,
        "duration": record.duration,
        "verification_status": record.verification_status,
        "confidence": record.confidence,
        "due_date": record.due_date,
        "status": record.status,
        "assigned_to_user_id": record.assigned_to_user_id,
        "completion_note": record.completion_note,
        "completion_evidence_record_id": record.completion_evidence_record_id,
        "completed_at": record.completed_at,
        "waived_reason": record.waived_reason,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "overdue": bool(
            record.due_date
            and record.due_date < date.today()
            and record.status not in {"completed", "waived"}
        ),
        "audit_entries": record.audit_entries,
    }


def _handle_error(exc):
    if isinstance(exc, ObligationNotFoundError):
        raise HTTPException(404, str(exc))
    if isinstance(exc, ObligationValidationError):
        raise HTTPException(422, str(exc))
    raise HTTPException(500, "Obligation operation failed.")


@router.post(
    "/{organization_id}/obligations/sync",
    response_model=ObligationSyncResponse,
)
def sync_obligations(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(require_organization_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    try:
        return sync_organization_obligations(
            db, organization_id, membership.user_id, commit=True
        )
    except (ObligationNotFoundError, ObligationValidationError) as exc:
        _handle_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not synchronize obligations.")


@router.get(
    "/{organization_id}/obligations",
    response_model=ContractualObligationListResponse,
)
def list_obligations(
    organization_id: UUID,
    status: str | None = None,
    overdue_only: bool = False,
    contract_id: UUID | None = None,
    assigned_to_user_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    if status is not None and status not in {"open", "in_progress", "completed", "waived"}:
        raise HTTPException(422, "Invalid obligation status.")
    records, total = list_organization_obligations(
        db, organization_id,
        status=status,
        overdue_only=overdue_only,
        contract_id=contract_id,
        assigned_to_user_id=assigned_to_user_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "organization_id": organization_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
        "obligations": [_serialize(item) for item in records],
    }


@router.get(
    "/{organization_id}/obligations/{obligation_id}",
    response_model=ContractualObligationResponse,
)
def get_obligation(
    organization_id: UUID,
    obligation_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db),
):
    try:
        return _serialize(get_organization_obligation(db, organization_id, obligation_id))
    except ObligationNotFoundError as exc:
        _handle_error(exc)


@router.patch(
    "/{organization_id}/obligations/{obligation_id}",
    response_model=ContractualObligationResponse,
)
def update_obligation(
    organization_id: UUID,
    obligation_id: UUID,
    request: ObligationUpdate,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    payload = request.model_dump(exclude_unset=True)
    try:
        record = update_organization_obligation(
            db,
            organization_id,
            obligation_id,
            membership.user_id,
            due_date=payload.get("due_date"),
            due_date_supplied="due_date" in payload,
            assigned_to_user_id=payload.get("assigned_to_user_id"),
            assignment_supplied="assigned_to_user_id" in payload,
            status=payload.get("status"),
            completion_note=payload.get("completion_note"),
            completion_evidence_record_id=payload.get("completion_evidence_record_id"),
            waived_reason=payload.get("waived_reason"),
            comment=payload.get("comment"),
            commit=True,
        )
        return _serialize(get_organization_obligation(db, organization_id, record.id))
    except (ObligationNotFoundError, ObligationValidationError) as exc:
        _handle_error(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not update obligation.")
