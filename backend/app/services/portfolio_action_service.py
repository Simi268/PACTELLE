from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.membership import OrganizationMembership
from app.models.portfolio_risk_finding import PortfolioRiskFinding
from app.models.portfolio_risk_action import (
    PortfolioRiskAction,
    PortfolioRiskActionAudit,
)
from app.services.portfolio_action_recommender import recommend_actions


class PortfolioActionError(Exception):
    pass


class PortfolioActionValidationError(PortfolioActionError):
    pass


class PortfolioActionNotFoundError(PortfolioActionError):
    pass


VALID_PRIORITIES = {"critical", "high", "medium", "low"}
VALID_STATUSES = {
    "proposed", "approved", "rejected", "in_progress", "completed"
}
ALLOWED_TRANSITIONS = {
    "proposed": {"approved", "rejected"},
    "approved": {"in_progress", "rejected"},
    "in_progress": {"completed", "rejected"},
    "rejected": set(),
    "completed": set(),
}


def _require_member(db: Session, organization_id: UUID, user_id: UUID) -> None:
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise PortfolioActionValidationError(
            "The user must belong to the action's organization."
        )


def _get_finding(
    db: Session, organization_id: UUID, finding_id: UUID
) -> PortfolioRiskFinding:
    finding = db.scalar(
        select(PortfolioRiskFinding)
        .where(
            PortfolioRiskFinding.id == finding_id,
            PortfolioRiskFinding.organization_id == organization_id,
        )
        .with_for_update()
    )
    if finding is None:
        raise PortfolioActionNotFoundError("Portfolio finding not found.")
    return finding


def _get_action(
    db: Session, organization_id: UUID, action_id: UUID, lock: bool = True
) -> PortfolioRiskAction:
    query = select(PortfolioRiskAction).where(
        PortfolioRiskAction.id == action_id,
        PortfolioRiskAction.organization_id == organization_id,
    )
    if lock:
        query = query.with_for_update()
    action = db.scalar(query)
    if action is None:
        raise PortfolioActionNotFoundError("Portfolio action not found.")
    return action


def _audit(
    db: Session,
    action: PortfolioRiskAction,
    actor_user_id: UUID | None,
    event_type: str,
    previous_status: str | None = None,
    new_status: str | None = None,
    comment: str | None = None,
) -> None:
    db.add(PortfolioRiskActionAudit(
        action_id=action.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=new_status,
        comment=comment,
    ))


def create_portfolio_action(
    db: Session,
    organization_id: UUID,
    finding_id: UUID,
    actor_user_id: UUID,
    *,
    title: str,
    description: str,
    rationale: str,
    priority: str,
    due_date: date | None = None,
    assigned_to_user_id: UUID | None = None,
    commit: bool = False,
) -> PortfolioRiskAction:
    if priority not in VALID_PRIORITIES:
        raise PortfolioActionValidationError("Invalid action priority.")
    if not title.strip() or not description.strip() or not rationale.strip():
        raise PortfolioActionValidationError(
            "Title, description and rationale are required."
        )

    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            _get_finding(db, organization_id, finding_id)
            if assigned_to_user_id is not None:
                _require_member(db, organization_id, assigned_to_user_id)

            action = PortfolioRiskAction(
                organization_id=organization_id,
                finding_id=finding_id,
                title=title.strip(),
                description=description.strip(),
                rationale=rationale.strip(),
                priority=priority,
                status="proposed",
                assigned_to_user_id=assigned_to_user_id,
                created_by_user_id=actor_user_id,
                due_date=due_date,
            )
            db.add(action)
            db.flush()
            _audit(
                db, action, actor_user_id, "created",
                new_status="proposed",
                comment="Action created as a proposal.",
            )
            db.flush()

        if commit:
            db.commit()
        else:
            db.flush()
        return action
    except Exception:
        if commit:
            db.rollback()
        raise


def generate_actions_for_finding(
    db: Session,
    organization_id: UUID,
    finding_id: UUID,
    actor_user_id: UUID,
    *,
    commit: bool = False,
) -> dict:
    """Create missing recommendation proposals; never duplicates active same-title actions."""
    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            finding = _get_finding(db, organization_id, finding_id)
            recommendations = recommend_actions(finding)
            created = []
            existing = []

            for recommendation in recommendations:
                duplicate = db.scalar(
                    select(PortfolioRiskAction).where(
                        PortfolioRiskAction.organization_id == organization_id,
                        PortfolioRiskAction.finding_id == finding_id,
                        PortfolioRiskAction.title == recommendation["title"],
                        PortfolioRiskAction.status.in_(
                            ["proposed", "approved", "in_progress"]
                        ),
                    )
                )
                if duplicate:
                    existing.append(duplicate)
                    continue

                due_date = date.today() + timedelta(
                    days=recommendation["due_days"]
                )
                action = PortfolioRiskAction(
                    organization_id=organization_id,
                    finding_id=finding_id,
                    title=recommendation["title"],
                    description=recommendation["description"],
                    rationale=recommendation["rationale"],
                    priority=recommendation["priority"],
                    status="proposed",
                    created_by_user_id=actor_user_id,
                    due_date=due_date,
                )
                db.add(action)
                db.flush()
                _audit(
                    db, action, actor_user_id, "recommended",
                    new_status="proposed",
                    comment="Generated by the deterministic recommendation engine.",
                )
                created.append(action)

            db.flush()

        if commit:
            db.commit()
        else:
            db.flush()
        return {
            "created_count": len(created),
            "existing_count": len(existing),
            "created_actions": created,
            "existing_actions": existing,
        }
    except Exception:
        if commit:
            db.rollback()
        raise


def update_portfolio_action_assignment(
    db: Session,
    organization_id: UUID,
    action_id: UUID,
    actor_user_id: UUID,
    assigned_to_user_id: UUID | None,
    *,
    commit: bool = False,
) -> PortfolioRiskAction:
    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            if assigned_to_user_id is not None:
                _require_member(db, organization_id, assigned_to_user_id)
            action = _get_action(db, organization_id, action_id)
            old_assignee = action.assigned_to_user_id
            action.assigned_to_user_id = assigned_to_user_id
            db.flush()
            _audit(
                db, action, actor_user_id, "assignment_changed",
                comment=(
                    f"Assignment changed from {old_assignee} "
                    f"to {assigned_to_user_id}."
                ),
            )
            db.flush()

        if commit:
            db.commit()
        return action
    except Exception:
        if commit:
            db.rollback()
        raise


def transition_portfolio_action(
    db: Session,
    organization_id: UUID,
    action_id: UUID,
    actor_user_id: UUID,
    new_status: str,
    *,
    comment: str | None = None,
    commit: bool = False,
) -> PortfolioRiskAction:
    if new_status not in VALID_STATUSES:
        raise PortfolioActionValidationError("Invalid action status.")
    if new_status == "rejected" and not (comment and comment.strip()):
        raise PortfolioActionValidationError(
            "A reason is required when rejecting an action."
        )

    try:
        with db.begin_nested():
            _require_member(db, organization_id, actor_user_id)
            action = _get_action(db, organization_id, action_id)
            previous_status = action.status

            if new_status not in ALLOWED_TRANSITIONS.get(previous_status, set()):
                raise PortfolioActionValidationError(
                    f"Cannot transition action from {previous_status} to {new_status}."
                )

            action.status = new_status
            db.flush()
            _audit(
                db,
                action,
                actor_user_id,
                "status_changed",
                previous_status=previous_status,
                new_status=new_status,
                comment=comment.strip() if comment else None,
            )
            db.flush()

        if commit:
            db.commit()
        return action
    except Exception:
        if commit:
            db.rollback()
        raise


def get_portfolio_action(
    db: Session, organization_id: UUID, action_id: UUID
) -> PortfolioRiskAction:
    action = db.scalar(
        select(PortfolioRiskAction)
        .where(
            PortfolioRiskAction.id == action_id,
            PortfolioRiskAction.organization_id == organization_id,
        )
        .options(
            selectinload(PortfolioRiskAction.audit_entries),
            selectinload(PortfolioRiskAction.finding),
        )
    )
    if action is None:
        raise PortfolioActionNotFoundError("Portfolio action not found.")
    return action


def list_portfolio_actions(
    db: Session,
    organization_id: UUID,
    *,
    finding_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PortfolioRiskAction], int]:
    from sqlalchemy import func

    query = select(PortfolioRiskAction).where(
        PortfolioRiskAction.organization_id == organization_id
    )
    count_query = select(func.count()).select_from(PortfolioRiskAction).where(
        PortfolioRiskAction.organization_id == organization_id
    )

    if finding_id is not None:
        query = query.where(PortfolioRiskAction.finding_id == finding_id)
        count_query = count_query.where(
            PortfolioRiskAction.finding_id == finding_id
        )
    if status is not None:
        if status not in VALID_STATUSES:
            raise PortfolioActionValidationError("Invalid action status filter.")
        query = query.where(PortfolioRiskAction.status == status)
        count_query = count_query.where(PortfolioRiskAction.status == status)
    if priority is not None:
        if priority not in VALID_PRIORITIES:
            raise PortfolioActionValidationError("Invalid action priority filter.")
        query = query.where(PortfolioRiskAction.priority == priority)
        count_query = count_query.where(PortfolioRiskAction.priority == priority)

    total = db.scalar(count_query) or 0
    actions = db.scalars(
        query.options(
            selectinload(PortfolioRiskAction.finding),
            selectinload(PortfolioRiskAction.audit_entries),
        )
        .order_by(PortfolioRiskAction.created_at.desc(), PortfolioRiskAction.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return list(actions), total
