import uuid

from datetime import date, datetime

from sqlalchemy import (
    String,
    Text,
    Float,
    Date,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    func,
    Uuid,
    text,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RiskFinding(Base):

    __tablename__ = "risk_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    risk_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="open"
    )

    assessment_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="provisional",
        server_default="provisional"
    )

    detection_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="rule_based"
    )

    rule_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    rule_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="1.0"
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    deadline_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    contract = relationship(
        "Contract"
    )

    evidence_links = relationship(
        "RiskFindingEvidence",
        back_populates="risk_finding",
        cascade="all, delete-orphan"
    )

    __table_args__ = (

        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="check_risk_finding_severity"
        ),

        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="check_risk_finding_status"
        ),

        CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0 AND confidence <= 1)",
            name="check_risk_finding_confidence"
        ),

        CheckConstraint(
            "assessment_status IN ('provisional', 'confirmed')",
            name="check_risk_finding_assessment_status"
        ),

        Index(
            "ix_risk_findings_contract_type",
            "contract_id",
            "risk_type"
        ),

        Index(
            "uq_active_risk_per_contract_rule",
            "contract_id",
            "rule_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'")
        ),
    )