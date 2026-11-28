"""Deterministic supervisor for PACTELLE agents."""

from datetime import datetime, timezone
from typing import Callable, Iterable, List

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    AgentTask,
    ExecutionStatus,
)
from app.agents.state import AgentState
from app.orchestration.execution_status import transition_status
from app.orchestration.verification_gate import (
    evaluate_verification_gate,
)


AgentHandler = Callable[[AgentState], AgentResult]


class Supervisor:
    """
    Coordinates agent execution.

    Supports sequential execution and an evidence verification gate.

    The supervisor does not make LLM calls or write to the database.
    """

    def __init__(self, handlers: Iterable[AgentHandler]):
        self.handlers: List[AgentHandler] = list(handlers)

        names = [
            self._handler_agent_name(handler)
            for handler in self.handlers
        ]

        if len(names) != len(set(names)):
            raise ValueError("Duplicate agent handlers are not allowed.")

    def run(self, task: AgentTask) -> AgentState:
        state = AgentState(task=task)

        state.status = transition_status(
            state.status,
            ExecutionStatus.RUNNING,
        )
        state.started_at = datetime.now(timezone.utc)

        for handler in self.handlers:
            agent_name = self._handler_agent_name(handler)
            state.current_agent = agent_name

            try:
                result = handler(state)

                if result.agent != agent_name:
                    raise ValueError(
                        f"Handler registered as {agent_name.value} "
                        f"returned result for {result.agent.value}"
                    )

                state.add_result(result)

                terminal_outcomes = {
                    AgentStatus.FAILED: ExecutionStatus.FAILED,
                    AgentStatus.NEEDS_OCR: ExecutionStatus.NEEDS_OCR,
                    AgentStatus.SUPERSEDED: ExecutionStatus.SUPERSEDED,
                }

                if result.status in terminal_outcomes:
                    state.status = transition_status(
                        state.status,
                        terminal_outcomes[result.status],
                    )
                    break

                if result.status != AgentStatus.COMPLETED:
                    raise ValueError(
                        f"Unsupported agent result status: "
                        f"{result.status.value}"
                    )

                # Evidence verification gate.
                if agent_name == AgentName.VERIFICATION:
                    decision = evaluate_verification_gate(state)

                    state.gate_decisions["evidence_verification"] = decision

                    if not decision["passed"]:
                        state.human_review_required = True

                        state.unresolved_questions.extend(
                            decision["reasons"]
                        )

                        state.status = transition_status(
                            state.status,
                            ExecutionStatus.REVIEW_REQUIRED,
                        )
                        break

            except Exception as exc:
                error = AgentError(
                    agent=agent_name,
                    code="AGENT_EXECUTION_ERROR",
                    message=str(exc),
                    retryable=False,
                )

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
                break

        if state.status == ExecutionStatus.RUNNING:
            target_status = (
                ExecutionStatus.REVIEW_REQUIRED
                if (
                    state.human_review_required
                    or state.unresolved_questions
                )
                else ExecutionStatus.COMPLETED
            )

            state.status = transition_status(
                state.status,
                target_status,
            )

        state.current_agent = None
        state.completed_at = datetime.now(timezone.utc)

        return state

    @staticmethod
    def _handler_agent_name(handler: AgentHandler) -> AgentName:
        agent_name = getattr(handler, "agent_name", None)

        if not isinstance(agent_name, AgentName):
            raise ValueError(
                "Each handler must expose an 'agent_name' "
                "attribute containing an AgentName"
            )

        return agent_name