import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Uuid,
    func,
)

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PortfolioAnalysisSnapshot(Base):

    __tablename__ = "portfolio_analysis_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    analysis_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="1.0",
        server_default="1.0",
    )

    total_contracts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_obligations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_comparisons: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_findings: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    summary: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    findings = relationship(
        "PortfolioAnalysisSnapshotFinding",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="PortfolioAnalysisSnapshotFinding.rule_id",
    )

    __table_args__ = (
        Index(
            "ix_portfolio_snapshots_org_created",
            "organization_id",
            "created_at",
        ),
    )


class PortfolioAnalysisSnapshotFinding(Base):

    __tablename__ = "portfolio_analysis_snapshot_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "portfolio_analysis_snapshots.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    portfolio_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "portfolio_risk_findings.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    rule_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    finding_type: Mapped[str] = mapped_column(
        String(50),
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

    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    assessment_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    contract_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
    )

    evidence_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    snapshot = relationship(
        "PortfolioAnalysisSnapshot",
        back_populates="findings",
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "rule_id",
            name="uq_snapshot_finding_rule",
        ),

        Index(
            "ix_snapshot_findings_rule",
            "rule_id",
        ),

        Index(
            "ix_snapshot_findings_live_finding",
            "portfolio_finding_id",
        ),
    )