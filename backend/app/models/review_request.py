import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReviewRequest(Base):
    """A human decision checkpoint for an organization-scoped workflow."""

    __tablename__ = "review_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    review_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    audit_entries = relationship(
        "ReviewRequestAudit", back_populates="review_request", cascade="all, delete-orphan",
        order_by="ReviewRequestAudit.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "review_type IN ('evidence_verification', 'interpretation', 'legal_review', 'action_approval')",
            name="ck_review_request_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'clarification_requested', 'cancelled')",
            name="ck_review_request_status",
        ),
        Index("ix_review_requests_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_review_requests_execution", "execution_id"),
        Index("ix_review_requests_assignee_status", "assigned_to_user_id", "status"),
    )


class ReviewRequestAudit(Base):
    """Append-only history of review request creation and decisions."""

    __tablename__ = "review_request_audits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("review_requests.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    review_request = relationship("ReviewRequest", back_populates="audit_entries")
    actor = relationship("User")

    __table_args__ = (
        Index("ix_review_request_audits_request_created", "review_request_id", "created_at"),
    )
