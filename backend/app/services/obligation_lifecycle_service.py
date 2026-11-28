from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.membership import OrganizationMembership
from app.models.contractual_obligation import (
    ContractualObligation,
    ContractualObligationAudit,
)
from app.services.portfolio_obligation_service import retrieve_organization_obligations


class ObligationError(Exception):
    pass


class ObligationNotFoundError(ObligationError):
    pass


class ObligationValidationError(ObligationError):
    pass


ALLOWED_TRANSITIONS = {
    "open": {"in_progress", "completed", "waived"},
    "in_progress": {"open", "completed", "waived"},
    "completed": {"open"},
    "waived": {"open"},
}


def _require_member(db: Session, organization_id: UUID, user_id: UUID):
    member = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user_id,
    ))
    if member is None:
        raise ObligationValidationError("User is not a member of this organization.")


def _audit(db, obligation, actor_id, event_type, previous=None, new=None, comment=None):
    db.add(ContractualObligationAudit(
        obligation_id=obligation.id,
        actor_user_id=actor_id,
        event_type=event_type,
        previous_status=previous,
        new_status=new,
        comment=comment,
    ))


def sync_organization_obligations(
    db: Session, organization_id: UUID, actor_user_id: UUID, *, commit=False
) -> dict:
    """Idempotently persist normalized current evidence as obligation records."""
    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            retrieved = retrieve_organization_obligations(db, organization_id)
            created = updated = unchanged = skipped_rejected = 0

            skipped_rejected = len(retrieved["excluded_obligations"])
            for item in retrieved["obligations"]:

                evidence_id = UUID(item["evidence_id"])
                evidence = db.get(EvidenceRecord, evidence_id)
                if evidence is None:
                    continue

                contract = evidence.document.contract
                existing = db.scalar(select(ContractualObligation).where(
                    ContractualObligation.evidence_record_id == evidence_id
                ))

                values = {
                    "organization_id": organization_id,
                    "contract_id": contract.id,
                    "obligation_type": item["obligation_type"],
                    "obligation_family": item["obligation_family"],
                    "description": item["description"],
                    "claim": item["claim"],
                    "original_text": item["original_text"],
                    "duration": item["duration"],
                    "verification_status": item["verification_status"],
                    "confidence": item["confidence"],
                }

                if existing is None:
                    obligation = ContractualObligation(
                        evidence_record_id=evidence_id,
                        **values,
                    )
                    db.add(obligation)
                    db.flush()
                    _audit(
                        db, obligation, actor_user_id, "created",
                        new=obligation.status,
                        comment="Created from current normalized evidence.",
                    )
                    created += 1
                else:
                    changed = any(getattr(existing, key) != value for key, value in values.items())
                    if changed:
                        for key, value in values.items():
                            setattr(existing, key, value)
                        _audit(
                            db, existing, actor_user_id, "source_refreshed",
                            previous=existing.status,
                            new=existing.status,
                            comment="Source evidence was refreshed; workflow fields were preserved.",
                        )
                        updated += 1
                    else:
                        unchanged += 1

            db.flush()

        if commit:
            db.commit()
        return {
            "organization_id": organization_id,
            "created_count": created,
            "updated_count": updated,
            "unchanged_count": unchanged,
            "skipped_rejected_count": skipped_rejected,
            "unsupported_count": retrieved["summary"]["unsupported_evidence"],
            "total_current_records": retrieved["summary"]["total_evidence_records"],
        }
    except Exception:
        if commit:
            db.rollback()
        raise


def list_organization_obligations(
    db: Session,
    organization_id: UUID,
    *,
    status: str | None = None,
    overdue_only: bool = False,
    contract_id: UUID | None = None,
    assigned_to_user_id: UUID | None = None,
    offset: int = 0,
    limit: int = 20,
):
    query = select(ContractualObligation).where(
        ContractualObligation.organization_id == organization_id
    )
    count_query = select(func.count()).select_from(ContractualObligation).where(
        ContractualObligation.organization_id == organization_id
    )
    if status:
        query = query.where(ContractualObligation.status == status)
        count_query = count_query.where(ContractualObligation.status == status)
    if contract_id:
        query = query.where(ContractualObligation.contract_id == contract_id)
        count_query = count_query.where(ContractualObligation.contract_id == contract_id)
    if assigned_to_user_id:
        query = query.where(ContractualObligation.assigned_to_user_id == assigned_to_user_id)
        count_query = count_query.where(ContractualObligation.assigned_to_user_id == assigned_to_user_id)
    if overdue_only:
        condition = (
            ContractualObligation.due_date < date.today(),
            ContractualObligation.status.notin_(["completed", "waived"]),
        )
        query = query.where(*condition)
        count_query = count_query.where(*condition)

    total = db.scalar(count_query) or 0
    records = db.scalars(
        query.options(selectinload(ContractualObligation.audit_entries))
        .order_by(ContractualObligation.due_date.asc().nullslast(), ContractualObligation.created_at.desc())
        .offset(offset).limit(limit)
    ).all()
    return list(records), total


def get_organization_obligation(
    db: Session, organization_id: UUID, obligation_id: UUID
):
    record = db.scalar(
        select(ContractualObligation)
        .where(
            ContractualObligation.organization_id == organization_id,
            ContractualObligation.id == obligation_id,
        )
        .options(selectinload(ContractualObligation.audit_entries))
    )
    if record is None:
        raise ObligationNotFoundError("Obligation not found.")
    return record


def update_organization_obligation(
    db: Session,
    organization_id: UUID,
    obligation_id: UUID,
    actor_user_id: UUID,
    *,
    due_date=None,
    due_date_supplied=False,
    assigned_to_user_id=None,
    assignment_supplied=False,
    status=None,
    completion_note=None,
    completion_evidence_record_id=None,
    waived_reason=None,
    comment=None,
    commit=False,
):
    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            record = db.scalar(
                select(ContractualObligation)
                .where(
                    ContractualObligation.organization_id == organization_id,
                    ContractualObligation.id == obligation_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ObligationNotFoundError("Obligation not found.")

            if assignment_supplied and assigned_to_user_id is not None:
                _require_member(db, organization_id, assigned_to_user_id)

            if status is not None:
                if status not in ALLOWED_TRANSITIONS.get(record.status, set()):
                    raise ObligationValidationError(
                        f"Cannot transition obligation from {record.status} to {status}."
                    )
                if status == "completed":
                    if not (completion_note and completion_note.strip()):
                        raise ObligationValidationError(
                            "A completion note is required to complete an obligation."
                        )
                    if record.verification_status == "rejected":
                        raise ObligationValidationError(
                            "Rejected source evidence cannot be marked completed."
                        )
                if status == "waived" and not (waived_reason and waived_reason.strip()):
                    raise ObligationValidationError(
                        "A reason is required to waive an obligation."
                    )

                previous = record.status
                record.status = status
                if status == "completed":
                    record.completed_at = datetime.now(timezone.utc)
                    record.completion_note = completion_note.strip()
                    record.completion_evidence_record_id = completion_evidence_record_id
                elif status == "waived":
                    record.waived_reason = waived_reason.strip()
                elif status == "open":
                    record.completed_at = None
                    record.completion_note = None
                    record.completion_evidence_record_id = None
                    record.waived_reason = None
                _audit(
                    db, record, actor_user_id, "status_changed",
                    previous=previous, new=status, comment=comment,
                )

            if due_date_supplied:
                previous_due_date = record.due_date
                record.due_date = due_date
                _audit(
                    db, record, actor_user_id, "due_date_changed",
                    comment=f"Due date changed from {previous_due_date} to {due_date}.",
                )

            if assignment_supplied:
                previous_assignee = record.assigned_to_user_id
                record.assigned_to_user_id = assigned_to_user_id
                _audit(
                    db, record, actor_user_id, "assignment_changed",
                    comment=f"Assignment changed from {previous_assignee} to {assigned_to_user_id}.",
                )

            if comment and status is None and not assignment_supplied and due_date is None:
                _audit(db, record, actor_user_id, "comment_added", comment=comment)

            db.flush()

        if commit:
            db.commit()
        return record
    except Exception:
        if commit:
            db.rollback()
        raise
