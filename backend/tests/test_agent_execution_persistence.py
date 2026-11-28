from uuid import uuid4

import pytest

from app.agents.contracts import AgentTask, ExecutionStatus
from app.agents.state import AgentState
from app.models.review_request import ReviewRequest
from app.services.agent_execution_service import (
    AgentExecutionConflictError,
    AgentExecutionValidationError,
    claim_approved_resume,
    create_execution,
    get_execution,
    load_execution_state,
    save_checkpoint,
    suspend_for_review,
)


def _task(org_id):
    return AgentTask(
        organization_id=org_id,
        task_type="organization_obligation_analysis",
    )


def test_execution_is_persisted_and_rehydrated(db_session, contract_api_data):
    org_id = contract_api_data["organization_a"].id
    task = _task(org_id)

    created = create_execution(db_session, task=task)
    assert created.status == "pending"
    assert created.version == 1

    state = load_execution_state(created)
    assert state.execution_id == task.execution_id
    assert state.organization_id == org_id

    state.status = ExecutionStatus.RUNNING
    saved = save_checkpoint(
        db_session,
        organization_id=org_id,
        execution_id=task.execution_id,
        state=state,
        next_agent_index=1,
        checkpoint_agent="obligation",
        expected_version=created.version,
    )
    assert saved.status == "running"
    assert saved.next_agent_index == 1
    assert saved.checkpoint_agent == "obligation"
    assert load_execution_state(saved).status == ExecutionStatus.RUNNING


def test_review_suspension_and_single_approved_resume(db_session, contract_api_data):
    org_id = contract_api_data["organization_a"].id
    task = _task(org_id)
    execution = create_execution(db_session, task=task)

    running_state = AgentState(task=task, status=ExecutionStatus.RUNNING)
    running = save_checkpoint(
        db_session,
        organization_id=org_id,
        execution_id=task.execution_id,
        state=running_state,
        next_agent_index=1,
        checkpoint_agent="verification",
        expected_version=execution.version,
    )

    review = ReviewRequest(
        organization_id=org_id,
        execution_id=task.execution_id,
        review_type="evidence_verification",
        status="pending",
        reason="Verification needs review.",
        evidence_snapshot=[],
        requested_by_user_id=contract_api_data["owner_a"].id,
    )
    db_session.add(review)
    db_session.commit()
    db_session.refresh(review)

    suspended_state = AgentState(
        task=task,
        status=ExecutionStatus.REVIEW_REQUIRED,
        human_review_required=True,
        current_agent=None,
    )
    suspended = suspend_for_review(
        db_session,
        organization_id=org_id,
        execution_id=task.execution_id,
        review_request_id=review.id,
        state=suspended_state,
        checkpoint_agent="verification",
        next_agent_index=1,
        expected_version=running.version,
    )
    assert suspended.status == "review_required"
    assert suspended.review_request_id == review.id

    with pytest.raises(AgentExecutionConflictError):
        claim_approved_resume(
            db_session, organization_id=org_id, execution_id=task.execution_id
        )

    review.status = "approved"
    db_session.commit()

    resumed = claim_approved_resume(
        db_session, organization_id=org_id, execution_id=task.execution_id
    )
    assert resumed.status == "running"
    assert resumed.resume_count == 1
    assert resumed.next_agent_index == 1
    assert resumed.checkpoint_agent == "verification"

    with pytest.raises(AgentExecutionConflictError):
        claim_approved_resume(
            db_session, organization_id=org_id, execution_id=task.execution_id
        )


def test_execution_scope_mismatch_is_rejected(db_session, contract_api_data):
    org_id = contract_api_data["organization_a"].id
    task = _task(org_id)
    execution = create_execution(db_session, task=task)
    wrong_state = AgentState(task=_task(uuid4()))

    with pytest.raises(AgentExecutionValidationError):
        save_checkpoint(
            db_session,
            organization_id=org_id,
            execution_id=task.execution_id,
            state=wrong_state,
            next_agent_index=0,
            checkpoint_agent=None,
            expected_version=execution.version,
        )


def test_stale_version_cannot_overwrite_execution(db_session, contract_api_data):
    org_id = contract_api_data["organization_a"].id
    task = _task(org_id)
    execution = create_execution(db_session, task=task)
    state = AgentState(task=task, status=ExecutionStatus.RUNNING)

    stale_version = execution.version
    save_checkpoint(
        db_session,
        organization_id=org_id,
        execution_id=task.execution_id,
        state=state,
        next_agent_index=0,
        checkpoint_agent=None,
        expected_version=stale_version,
    )

    with pytest.raises(AgentExecutionConflictError):
        save_checkpoint(
            db_session,
            organization_id=org_id,
            execution_id=task.execution_id,
            state=state,
            next_agent_index=1,
            checkpoint_agent="document",
            expected_version=stale_version,
        )
