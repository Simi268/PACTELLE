import uuid

from datetime import datetime, date

from sqlalchemy import (
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PortfolioRiskAction(Base):
    __tablename__ = "portfolio_risk_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolio_risk_findings.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="proposed",
        server_default="proposed",
    )

    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    finding = relationship("PortfolioRiskFinding")

    assigned_to = relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
    )

    created_by = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )

    audit_entries = relationship(
        "PortfolioRiskActionAudit",
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="PortfolioRiskActionAudit.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="check_portfolio_action_priority",
        ),
        CheckConstraint(
            "status IN "
            "('proposed', 'approved', 'rejected', "
            "'in_progress', 'completed')",
            name="check_portfolio_action_status",
        ),
        Index(
            "ix_portfolio_actions_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_portfolio_actions_finding",
            "finding_id",
        ),
    )


class PortfolioRiskActionAudit(Base):
    __tablename__ = "portfolio_risk_action_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolio_risk_actions.id", ondelete="CASCADE"),
        nullable=False,
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    previous_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    new_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    action = relationship(
        "PortfolioRiskAction",
        back_populates="audit_entries",
    )

    actor = relationship("User")

    __table_args__ = (
        Index(
            "ix_portfolio_action_audits_action_created",
            "action_id",
            "created_at",
        ),
    )