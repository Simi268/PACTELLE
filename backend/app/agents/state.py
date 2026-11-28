"""Shared state passed between PACTELLE agents."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentTask,
    ExecutionStatus,
    EvidenceReference,
)


class AgentExecutionRecord(BaseModel):
    """In-memory audit record for one agent invocation.

    Records are returned with the execution state so callers can inspect the
    execution path. Persistence is intentionally handled by a later layer.
    """

    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
    error_code: Optional[str] = None


class AgentState(BaseModel):
    """In-memory execution state shared by all agents in one workflow."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    task: AgentTask
    status: ExecutionStatus = ExecutionStatus.PENDING
    current_agent: Optional[AgentName] = None
    results: Dict[str, AgentResult] = Field(default_factory=dict)
    gate_decisions: Dict[str, dict] = Field(default_factory=dict)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    errors: List[AgentError] = Field(default_factory=list)
    execution_trace: List[AgentExecutionRecord] = Field(default_factory=list)
    human_review_required: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def execution_id(self) -> UUID:
        return self.task.execution_id

    @property
    def organization_id(self) -> UUID:
        return self.task.organization_id

    def add_result(self, result: AgentResult) -> None:
        """Merge a completed agent result into shared execution state."""
        self.results[result.agent.value] = result
        self.evidence_references.extend(result.evidence_references)
        self.unresolved_questions.extend(result.unresolved_questions)
        self.human_review_required = (
            self.human_review_required or result.human_review_required
        )

        if result.error is not None:
            self.errors.append(result.error)
