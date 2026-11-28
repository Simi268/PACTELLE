"""Transactional persistence helpers for resumable agent executions."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.contracts import AgentTask, ExecutionStatus
from app.agents.state import AgentState
from app.models.agent_execution import AgentExecution
from app.models.review_request import ReviewRequest


class AgentExecutionNotFoundError(Exception):
    pass


class AgentExecutionConflictError(Exception):
    pass


class AgentExecutionValidationError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def create_execution(
    db: Session,
    *,
    task: AgentTask,
    requested_by_user_id: UUID | None = None,
) -> AgentExecution:
    """Create a durable execution before any agent handler is invoked."""
    existing = db.query(AgentExecution).filter(
        AgentExecution.execution_id == task.execution_id
    ).first()
    if existing is not None:
        raise AgentExecutionConflictError("An execution with this identifier already exists.")

    state = AgentState(task=task)
    row = AgentExecution(
        execution_id=task.execution_id,
        organization_id=task.organization_id,
        requested_by_user_id=requested_by_user_id or task.requested_by_user_id,
        task_type=task.task_type,
        status=ExecutionStatus.PENDING.value,
        checkpoint_agent=None,
        next_agent_index=0,
        state_snapshot=state.model_dump(mode="json"),
        version=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_execution(
    db: Session, *, organization_id: UUID, execution_id: UUID
) -> AgentExecution:
    row = db.query(AgentExecution).filter(
        AgentExecution.execution_id == execution_id,
        AgentExecution.organization_id == organization_id,
    ).first()
    if row is None:
        raise AgentExecutionNotFoundError("Agent execution not found.")
    return row


def load_execution_state(row: AgentExecution) -> AgentState:
    """Rehydrate a previously persisted AgentState with Pydantic validation."""
    state = AgentState.model_validate(row.state_snapshot)
    if state.execution_id != row.execution_id or state.organization_id != row.organization_id:
        raise AgentExecutionValidationError(
            "Persisted execution state does not match its execution scope."
        )
    return state


def save_checkpoint(
    db: Session,
    *,
    organization_id: UUID,
    execution_id: UUID,
    state: AgentState,
    next_agent_index: int,
    checkpoint_agent: str | None,
    expected_version: int,
) -> AgentExecution:
    """Save a checkpoint using optimistic concurrency control."""
    if next_agent_index < 0:
        raise AgentExecutionValidationError("Checkpoint index cannot be negative.")
    if state.execution_id != execution_id or state.organization_id != organization_id:
        raise AgentExecutionValidationError("Execution state scope does not match the record.")

    row = db.query(AgentExecution).filter(
        AgentExecution.execution_id == execution_id,
        AgentExecution.organization_id == organization_id,
    ).with_for_update().first()
    if row is None:
        raise AgentExecutionNotFoundError("Agent execution not found.")
    if row.version != expected_version:
        raise AgentExecutionConflictError("Execution was modified by another worker; reload before saving.")
    if row.status not in {ExecutionStatus.PENDING.value, ExecutionStatus.RUNNING.value}:
        raise AgentExecutionConflictError("Only pending or running executions can be checkpointed.")

    row.state_snapshot = state.model_dump(mode="json")
    row.status = state.status.value
    row.next_agent_index = next_agent_index
    row.checkpoint_agent = checkpoint_agent
    row.version += 1
    if state.started_at and row.started_at is None:
        row.started_at = state.started_at
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def suspend_for_review(
    db: Session,
    *,
    organization_id: UUID,
    execution_id: UUID,
    review_request_id: UUID,
    state: AgentState,
    checkpoint_agent: str,
    next_agent_index: int,
    expected_version: int,
) -> AgentExecution:
    """Atomically associate a pending review with a review-blocked execution."""
    if state.status != ExecutionStatus.REVIEW_REQUIRED:
        raise AgentExecutionValidationError("Only review-required states can be suspended.")
    if state.execution_id != execution_id or state.organization_id != organization_id:
        raise AgentExecutionValidationError("Execution state scope does not match the record.")

    row = db.query(AgentExecution).filter(
        AgentExecution.execution_id == execution_id,
        AgentExecution.organization_id == organization_id,
    ).with_for_update().first()
    if row is None:
        raise AgentExecutionNotFoundError("Agent execution not found.")
    if row.version != expected_version:
        raise AgentExecutionConflictError("Execution was modified by another worker; reload before suspending.")
    if row.status != ExecutionStatus.RUNNING.value:
        raise AgentExecutionConflictError("Only a running execution can be suspended.")

    review = db.query(ReviewRequest).filter(
        ReviewRequest.id == review_request_id,
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.execution_id == execution_id,
        ReviewRequest.status == "pending",
    ).with_for_update().first()
    if review is None:
        raise AgentExecutionValidationError("A matching pending review request is required.")

    row.status = ExecutionStatus.REVIEW_REQUIRED.value
    row.state_snapshot = state.model_dump(mode="json")
    row.checkpoint_agent = checkpoint_agent
    row.next_agent_index = next_agent_index
    row.review_request_id = review_request_id
    row.version += 1
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def claim_approved_resume(
    db: Session,
    *,
    organization_id: UUID,
    execution_id: UUID,
) -> AgentExecution:
    """Atomically claim a single resume after its linked review is approved.

    This function deliberately does not mark evidence verified. The workflow
    must execute its verification handler again at the persisted checkpoint.
    """
    row = db.query(AgentExecution).filter(
        AgentExecution.execution_id == execution_id,
        AgentExecution.organization_id == organization_id,
    ).with_for_update().first()
    if row is None:
        raise AgentExecutionNotFoundError("Agent execution not found.")
    if row.status != ExecutionStatus.REVIEW_REQUIRED.value or row.review_request_id is None:
        raise AgentExecutionConflictError("Execution is not waiting for a linked human review.")

    review = db.query(ReviewRequest).filter(
        ReviewRequest.id == row.review_request_id,
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.execution_id == execution_id,
    ).with_for_update().first()
    if review is None or review.status != "approved":
        raise AgentExecutionConflictError("The linked review has not been approved.")

    row.status = ExecutionStatus.RUNNING.value
    row.resume_count += 1
    row.version += 1
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def mark_execution_terminal(
    db: Session,
    *,
    organization_id: UUID,
    execution_id: UUID,
    state: AgentState,
    expected_version: int,
) -> AgentExecution:
    """Persist a terminal state and completion timestamp."""
    terminal = {
        ExecutionStatus.COMPLETED.value,
        ExecutionStatus.NEEDS_OCR.value,
        ExecutionStatus.SUPERSEDED.value,
        ExecutionStatus.FAILED.value,
        ExecutionStatus.CANCELLED.value,
    }
    if state.status.value not in terminal:
        raise AgentExecutionValidationError("State is not in a terminal status.")

    row = db.query(AgentExecution).filter(
        AgentExecution.execution_id == execution_id,
        AgentExecution.organization_id == organization_id,
    ).with_for_update().first()
    if row is None:
        raise AgentExecutionNotFoundError("Agent execution not found.")
    if row.version != expected_version:
        raise AgentExecutionConflictError("Execution was modified by another worker; reload before completing.")
    if row.status not in {ExecutionStatus.RUNNING.value, ExecutionStatus.PENDING.value}:
        raise AgentExecutionConflictError("Execution is not active.")

    row.status = state.status.value
    row.state_snapshot = state.model_dump(mode="json")
    row.completed_at = state.completed_at or _now()
    row.version += 1
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row
