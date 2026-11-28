"""Persistent, organization-scoped agent workflow execution records."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentExecution(Base):
    """Durable workflow state and checkpoint metadata.

    ``state_snapshot`` stores the validated Pydantic AgentState payload. The
    checkpoint index is the next handler to execute, not the last handler that
    completed. A review-blocked verification step is checkpointed at that same
    index so it must run again before downstream agents can continue.
    """

    __tablename__ = "agent_executions"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    checkpoint_agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_agent_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    review_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("review_requests.id", ondelete="SET NULL"), nullable=True
    )
    resume_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'needs_ocr', 'superseded', 'failed', 'review_required', 'cancelled')",
            name="ck_agent_execution_status",
        ),
        CheckConstraint("next_agent_index >= 0", name="ck_agent_execution_next_index"),
        CheckConstraint("resume_count >= 0", name="ck_agent_execution_resume_count"),
        CheckConstraint("version >= 1", name="ck_agent_execution_version"),
        Index("ix_agent_executions_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_agent_executions_review_request", "review_request_id"),
    )
