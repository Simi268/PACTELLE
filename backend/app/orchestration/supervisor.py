"""Deterministic supervisor for PACTELLE agents."""

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, Iterable, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
    ExecutionStatus,
)
from app.agents.state import AgentExecutionRecord, AgentState
from app.orchestration.execution_status import transition_status
from app.orchestration.verification_gate import evaluate_verification_gate
from app.services.agent_execution_service import (
    claim_approved_resume,
    create_execution,
    get_execution,
    load_execution_state,
    mark_execution_terminal,
    save_checkpoint,
    suspend_for_review,
)
from app.services.review_request_service import create_review_request


AgentHandler = Callable[[AgentState], AgentResult]


class Supervisor:
    """Coordinates sequential agent execution and safety gates.

    The supervisor is deliberately deterministic: it does not make LLM calls,
    access the database, persist execution state, or execute recommendations.
    """

    def __init__(self, handlers: Iterable[AgentHandler]):
        self.handlers: List[AgentHandler] = list(handlers)

        names = [self._handler_agent_name(handler) for handler in self.handlers]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate agent handlers are not allowed.")

    def run_persisted(
        self,
        task: AgentTask,
        db: Session,
        *,
        requested_by_user_id: UUID | None = None,
        assigned_to_user_id: UUID | None = None,
    ) -> AgentState:
        """Run the workflow with durable checkpoints and review suspension.

        The original ``run`` method remains unchanged for existing callers.
        Persisted runs require an authenticated requester because a blocked
        verification gate must create an auditable human-review request.
        """
        requester_id = requested_by_user_id or task.requested_by_user_id
        if requester_id is None:
            raise ValueError("Persisted executions require requested_by_user_id.")
        row = create_execution(db, task=task, requested_by_user_id=requester_id)
        state = load_execution_state(row)
        state.status = ExecutionStatus.RUNNING
        state.started_at = datetime.now(timezone.utc)
        row = save_checkpoint(
            db,
            organization_id=task.organization_id,
            execution_id=task.execution_id,
            state=state,
            next_agent_index=0,
            checkpoint_agent=self._agent_name_at(0),
            expected_version=row.version,
        )
        return self._continue_persisted(
            db, row, state, start_index=0, requested_by_user_id=requester_id,
            assigned_to_user_id=assigned_to_user_id,
        )

    def resume_persisted(
        self,
        db: Session,
        *,
        organization_id: UUID,
        execution_id: UUID,
    ) -> AgentState:
        """Claim an approved review exactly once and resume its saved handler.

        The checkpoint for a verification failure points to the verification
        handler itself, forcing fresh provenance checks before later agents.
        """
        row = get_execution(db, organization_id=organization_id, execution_id=execution_id)
        row = claim_approved_resume(
            db, organization_id=organization_id, execution_id=execution_id
        )
        state = load_execution_state(row)
        state.status = ExecutionStatus.RUNNING
        state.completed_at = None
        state.current_agent = None
        requester_id = row.requested_by_user_id
        if requester_id is None:
            raise ValueError("Execution has no requester available for review audit.")
        return self._continue_persisted(
            db, row, state, start_index=row.next_agent_index,
            requested_by_user_id=requester_id,
            assigned_to_user_id=None,
        )

    def _continue_persisted(
        self, db: Session, row, state: AgentState, *, start_index: int,
        requested_by_user_id: UUID, assigned_to_user_id: UUID | None,
    ) -> AgentState:
        for index in range(start_index, len(self.handlers)):
            handler = self.handlers[index]
            agent_name = self._handler_agent_name(handler)
            state.current_agent = agent_name
            started = datetime.now(timezone.utc)
            clock_started = perf_counter()
            step_status = ExecutionStatus.FAILED
            error_code = None
            trace_written = False
            def write_trace():
                nonlocal trace_written
                if trace_written:
                    return
                state.execution_trace.append(AgentExecutionRecord(
                    agent=agent_name, status=step_status, started_at=started,
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=max(0.0, (perf_counter() - clock_started) * 1000),
                    error_code=error_code,
                ))
                trace_written = True
            try:
                result = handler(state)
                if not isinstance(result, AgentResult):
                    raise TypeError(f"Handler {agent_name.value} must return AgentResult.")
                if result.agent != agent_name:
                    raise ValueError(
                        f"Handler registered as {agent_name.value} returned result for {result.agent.value}"
                    )
                result.started_at = result.started_at or started
                result.completed_at = result.completed_at or datetime.now(timezone.utc)
                state.add_result(result)

                terminal = {
                    AgentStatus.FAILED: ExecutionStatus.FAILED,
                    AgentStatus.NEEDS_OCR: ExecutionStatus.NEEDS_OCR,
                    AgentStatus.SUPERSEDED: ExecutionStatus.SUPERSEDED,
                }
                if result.status in terminal:
                    state.status = terminal[result.status]
                    step_status = state.status
                    error_code = result.error.code if result.error else None
                    state.current_agent = None
                    state.completed_at = datetime.now(timezone.utc)
                    write_trace()
                    row = mark_execution_terminal(
                        db, organization_id=state.organization_id,
                        execution_id=state.execution_id, state=state,
                        expected_version=row.version,
                    )
                    return state
                if result.status != AgentStatus.COMPLETED:
                    raise ValueError(f"Unsupported agent result status: {result.status.value}")

                step_status = ExecutionStatus.COMPLETED
                if agent_name == AgentName.VERIFICATION:
                    decision = evaluate_verification_gate(state)
                    state.gate_decisions["evidence_verification"] = decision
                    if not decision["passed"]:
                        state.human_review_required = True
                        state.unresolved_questions.extend(decision["reasons"])
                        state.status = ExecutionStatus.REVIEW_REQUIRED
                        step_status = ExecutionStatus.REVIEW_REQUIRED
                        state.current_agent = None
                        state.completed_at = None
                        write_trace()
                        evidence_ids = self._eligible_evidence_ids(state)
                        review = create_review_request(
                            db,
                            organization_id=state.organization_id,
                            requested_by_user_id=requested_by_user_id,
                            review_type="evidence_verification",
                            reason="Evidence verification requires human review: " + " ".join(decision["reasons"]),
                            evidence_record_ids=evidence_ids,
                            execution_id=state.execution_id,
                            subject_type="agent_execution",
                            subject_id=state.execution_id,
                            proposed_interpretation="Review the cited evidence and resolve the verification issues. Approval does not bypass re-verification.",
                            assigned_to_user_id=assigned_to_user_id,
                        )
                        suspend_for_review(
                            db,
                            organization_id=state.organization_id,
                            execution_id=state.execution_id,
                            review_request_id=review.id,
                            state=state,
                            checkpoint_agent=agent_name.value,
                            next_agent_index=index,
                            expected_version=row.version,
                        )
                        return state

                state.current_agent = None
                state.status = ExecutionStatus.RUNNING
                write_trace()
                row = save_checkpoint(
                    db,
                    organization_id=state.organization_id,
                    execution_id=state.execution_id,
                    state=state,
                    next_agent_index=index + 1,
                    checkpoint_agent=self._agent_name_at(index + 1),
                    expected_version=row.version,
                )
            except Exception as exc:
                error = AgentError(
                    agent=agent_name, code="AGENT_EXECUTION_ERROR",
                    message=str(exc), retryable=False,
                )
                state.add_result(AgentResult(
                    agent=agent_name, status=AgentStatus.FAILED, error=error
                ))
                state.status = ExecutionStatus.FAILED
                state.current_agent = None
                state.completed_at = datetime.now(timezone.utc)
                error_code = error.code
                step_status = ExecutionStatus.FAILED
                write_trace()
                mark_execution_terminal(
                    db, organization_id=state.organization_id,
                    execution_id=state.execution_id, state=state,
                    expected_version=row.version,
                )
                return state

        state.current_agent = None
        state.status = ExecutionStatus.COMPLETED
        state.completed_at = datetime.now(timezone.utc)
        mark_execution_terminal(
            db, organization_id=state.organization_id,
            execution_id=state.execution_id, state=state,
            expected_version=row.version,
        )
        return state

    def _agent_name_at(self, index: int) -> str | None:
        if index < 0 or index >= len(self.handlers):
            return None
        return self._handler_agent_name(self.handlers[index]).value

    @staticmethod
    def _eligible_evidence_ids(state: AgentState) -> list[UUID]:
        """Return valid UUID evidence identifiers for tenant-scoped snapshots."""
        obligation_result = state.results.get(AgentName.OBLIGATION.value)
        if obligation_result is None:
            return []
        identifiers = []
        for obligation in obligation_result.data.get("obligations", []):
            if not isinstance(obligation, dict) or not obligation.get("evidence_id"):
                continue
            try:
                identifiers.append(UUID(str(obligation["evidence_id"])))
            except (TypeError, ValueError):
                continue
        return list(dict.fromkeys(identifiers))

    def run(self, task: AgentTask) -> AgentState:
        state = AgentState(task=task)
        state.status = transition_status(state.status, ExecutionStatus.RUNNING)
        state.started_at = datetime.now(timezone.utc)

        for handler in self.handlers:
            agent_name = self._handler_agent_name(handler)
            state.current_agent = agent_name
            step_started_at = datetime.now(timezone.utc)
            clock_started = perf_counter()
            step_status = ExecutionStatus.FAILED
            error_code = None

            try:
                result = handler(state)

                if not isinstance(result, AgentResult):
                    raise TypeError(
                        f"Handler {agent_name.value} must return AgentResult."
                    )

                if result.agent != agent_name:
                    raise ValueError(
                        f"Handler registered as {agent_name.value} "
                        f"returned result for {result.agent.value}"
                    )

                if result.started_at is None:
                    result.started_at = step_started_at
                if result.completed_at is None:
                    result.completed_at = datetime.now(timezone.utc)

                state.add_result(result)

                terminal_outcomes = {
                    AgentStatus.FAILED: ExecutionStatus.FAILED,
                    AgentStatus.NEEDS_OCR: ExecutionStatus.NEEDS_OCR,
                    AgentStatus.SUPERSEDED: ExecutionStatus.SUPERSEDED,
                }

                if result.status in terminal_outcomes:
                    step_status = terminal_outcomes[result.status]
                    error_code = result.error.code if result.error else None
                    state.status = transition_status(state.status, step_status)
                    break

                if result.status != AgentStatus.COMPLETED:
                    raise ValueError(
                        f"Unsupported agent result status: {result.status.value}"
                    )

                step_status = ExecutionStatus.COMPLETED

                if agent_name == AgentName.VERIFICATION:
                    decision = evaluate_verification_gate(state)
                    state.gate_decisions["evidence_verification"] = decision

                    if not decision["passed"]:
                        state.human_review_required = True
                        state.unresolved_questions.extend(decision["reasons"])
                        state.status = transition_status(
                            state.status,
                            ExecutionStatus.REVIEW_REQUIRED,
                        )
                        step_status = ExecutionStatus.REVIEW_REQUIRED
                        break

            except Exception as exc:
                error = AgentError(
                    agent=agent_name,
                    code="AGENT_EXECUTION_ERROR",
                    message=str(exc),
                    retryable=False,
                )
                error_code = error.code
                state.add_result(
                    AgentResult(
                        agent=agent_name,
                        status=AgentStatus.FAILED,
                        error=error,
                    )
                )
                state.status = transition_status(
                    state.status,
                    ExecutionStatus.FAILED,
                )
                step_status = ExecutionStatus.FAILED
                break

            finally:
                step_completed_at = datetime.now(timezone.utc)
                state.execution_trace.append(
                    AgentExecutionRecord(
                        agent=agent_name,
                        status=step_status,
                        started_at=step_started_at,
                        completed_at=step_completed_at,
                        duration_ms=max(
                            0.0,
                            (perf_counter() - clock_started) * 1000,
                        ),
                        error_code=error_code,
                    )
                )

        if state.status == ExecutionStatus.RUNNING:
            target_status = (
                ExecutionStatus.REVIEW_REQUIRED
                if state.human_review_required or state.unresolved_questions
                else ExecutionStatus.COMPLETED
            )
            state.status = transition_status(state.status, target_status)

        state.current_agent = None
        state.completed_at = datetime.now(timezone.utc)
        return state

    @staticmethod
    def _handler_agent_name(handler: AgentHandler) -> AgentName:
        agent_name = getattr(handler, "agent_name", None)
        if not isinstance(agent_name, AgentName):
            raise ValueError(
                "Each handler must expose an 'agent_name' attribute "
                "containing an AgentName"
            )
        return agent_name
