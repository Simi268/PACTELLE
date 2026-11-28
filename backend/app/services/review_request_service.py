from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.membership import OrganizationMembership
from app.models.review_request import ReviewRequest, ReviewRequestAudit


class ReviewRequestNotFoundError(Exception):
    pass


class ReviewRequestValidationError(Exception):
    pass


class ReviewRequestPermissionError(Exception):
    pass


def _evidence_snapshot(db: Session, organization_id: UUID, evidence_ids: list[UUID]) -> list[dict]:
    rows = (
        db.query(EvidenceRecord, ContractDocument, Contract)
        .join(ContractDocument, ContractDocument.id == EvidenceRecord.document_id)
        .join(Contract, Contract.id == ContractDocument.contract_id)
        .filter(
            EvidenceRecord.id.in_(evidence_ids),
            Contract.organization_id == organization_id,
        )
        .all()
    )
    by_id = {evidence.id: (evidence, document, contract) for evidence, document, contract in rows}
    missing = set(evidence_ids) - set(by_id)
    if missing:
        # Do not disclose whether an inaccessible evidence identifier exists.
        raise ReviewRequestValidationError("One or more evidence records are unavailable in this organization.")

    snapshots = []
    for evidence_id in evidence_ids:
        evidence, document, contract = by_id[evidence_id]
        snapshots.append({
            "evidence_record_id": str(evidence.id),
            "contract_id": str(contract.id),
            "document_id": str(document.id),
            "document_name": document.original_filename,
            "clause_id": str(evidence.clause_id),
            "claim": evidence.claim,
            "evidence_text": evidence.evidence_text,
            "page_number": evidence.page_number,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
            "verification_status_at_request": evidence.verification_status,
            "is_current_at_request": evidence.is_current,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        })
    return snapshots


def create_review_request(
    db: Session,
    *,
    organization_id: UUID,
    requested_by_user_id: UUID,
    review_type: str,
    reason: str,
    evidence_record_ids: list[UUID],
    execution_id: UUID | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    proposed_interpretation: str | None = None,
    assigned_to_user_id: UUID | None = None,
) -> ReviewRequest:
    evidence_snapshot = _evidence_snapshot(db, organization_id, evidence_record_ids)

    if assigned_to_user_id is not None:
        assignee = db.query(OrganizationMembership).filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == assigned_to_user_id,
        ).first()
        if assignee is None or assignee.role not in {"owner", "admin"}:
            raise ReviewRequestValidationError("Assigned reviewer must be an owner or admin in this organization.")

    review = ReviewRequest(
        organization_id=organization_id,
        execution_id=execution_id,
        review_type=review_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status="pending",
        reason=reason,
        proposed_interpretation=proposed_interpretation,
        evidence_snapshot=evidence_snapshot,
        requested_by_user_id=requested_by_user_id,
        assigned_to_user_id=assigned_to_user_id,
    )
    db.add(review)
    db.flush()
    db.add(ReviewRequestAudit(
        review_request_id=review.id,
        actor_user_id=requested_by_user_id,
        event_type="created",
        previous_status=None,
        new_status="pending",
        comment=reason,
    ))
    db.commit()
    db.refresh(review)
    return review


def list_review_requests(
    db: Session,
    organization_id: UUID,
    *,
    status: str | None = None,
    assigned_to_user_id: UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ReviewRequest], int]:
    query = db.query(ReviewRequest).filter(ReviewRequest.organization_id == organization_id)
    if status:
        query = query.filter(ReviewRequest.status == status)
    if assigned_to_user_id:
        query = query.filter(ReviewRequest.assigned_to_user_id == assigned_to_user_id)
    total = query.count()
    items = query.order_by(ReviewRequest.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def get_review_request(db: Session, organization_id: UUID, review_id: UUID) -> ReviewRequest:
    review = db.query(ReviewRequest).filter(
        ReviewRequest.id == review_id,
        ReviewRequest.organization_id == organization_id,
    ).first()
    if review is None:
        raise ReviewRequestNotFoundError("Review request not found.")
    return review


def decide_review_request(
    db: Session,
    *,
    organization_id: UUID,
    review_id: UUID,
    actor_user_id: UUID,
    decision: str,
    comment: str,
) -> ReviewRequest:
    review = (
        db.query(ReviewRequest)
        .filter(
            ReviewRequest.id == review_id,
            ReviewRequest.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if review is None:
        raise ReviewRequestNotFoundError("Review request not found.")
    if review.status not in {"pending", "clarification_requested"}:
        raise ReviewRequestValidationError("This review request has already been resolved.")
    if review.assigned_to_user_id is not None and review.assigned_to_user_id != actor_user_id:
        raise ReviewRequestPermissionError("This review request is assigned to another reviewer.")

    previous_status = review.status
    review.status = decision
    review.decided_by_user_id = actor_user_id
    review.decision_comment = comment
    review.decided_at = datetime.now(timezone.utc) if decision in {"approved", "rejected"} else None
    db.add(ReviewRequestAudit(
        review_request_id=review.id,
        actor_user_id=actor_user_id,
        event_type=decision,
        previous_status=previous_status,
        new_status=decision,
        comment=comment,
    ))
    db.commit()
    db.refresh(review)
    return review
