"""Typed contracts shared by PACTELLE agents."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentName(str, Enum):
    SUPERVISOR = "supervisor"
    DOCUMENT = "document"
    OBLIGATION = "obligation"
    INTELLIGENCE = "intelligence"
    INVESTIGATION = "investigation"
    VERIFICATION = "verification"
    RECOMMENDATION = "recommendation"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_OCR = "needs_ocr"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_OCR = "needs_ocr"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    SKIPPED = "skipped"


class EvidenceReference(BaseModel):
    """Reference to existing source evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    document_id: Optional[str] = None
    contract_id: Optional[str] = None
    clause_id: Optional[str] = None

    page_number: Optional[int] = Field(default=None, ge=1)
    char_start: Optional[int] = Field(default=None, ge=0)
    char_end: Optional[int] = Field(default=None, ge=0)

    excerpt: Optional[str] = None
    verification_status: Optional[str] = None

    @model_validator(mode="after")
    def validate_offsets(self):
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError(
                "char_end must be greater than or equal to char_start"
            )

        return self


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    code: str
    message: str
    retryable: bool = False

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentResult(BaseModel):
    """Standard output format for every agent."""

    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    status: AgentStatus

    summary: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)

    evidence_references: List[EvidenceReference] = Field(
        default_factory=list
    )

    unresolved_questions: List[str] = Field(default_factory=list)

    human_review_required: bool = False

    error: Optional[AgentError] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_result_state(self):

        if self.status == AgentStatus.FAILED and self.error is None:
            raise ValueError(
                "A failed agent result must include an error"
            )

        if self.status != AgentStatus.FAILED and self.error is not None:
            raise ValueError(
                "Only a failed agent result may include an error"
            )

        return self


class AgentTask(BaseModel):
    """A task submitted to the supervisor."""

    model_config = ConfigDict(extra="forbid")

    execution_id: UUID = Field(default_factory=uuid4)

    organization_id: UUID

    task_type: str

    requested_by_user_id: Optional[UUID] = None

    input_data: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentExecutionSummary(BaseModel):
    """Compact representation of an agent execution."""

    model_config = ConfigDict(extra="forbid")

    execution_id: UUID
    organization_id: UUID

    status: ExecutionStatus

    completed_agents: List[AgentName] = Field(default_factory=list)
    failed_agents: List[AgentName] = Field(default_factory=list)

    human_review_required: bool = False

    unresolved_questions: List[str] = Field(default_factory=list)
    errors: List[AgentError] = Field(default_factory=list)