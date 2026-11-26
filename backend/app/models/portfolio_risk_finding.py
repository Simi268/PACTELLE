import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PortfolioRiskFinding(Base):

    __tablename__ = "portfolio_risk_findings"

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

    finding_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
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
        default="open",
        server_default="open",
    )

    assessment_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="provisional",
        server_default="provisional",
    )

    detection_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="rule_based",
        server_default="rule_based",
    )

    rule_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    rule_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="1.0",
        server_default="1.0",
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="portfolio_risk_findings",
    )

    contract_links = relationship(
        "PortfolioRiskFindingContract",
        back_populates="portfolio_finding",
        cascade="all, delete-orphan",
    )

    evidence_links = relationship(
        "PortfolioRiskFindingEvidence",
        back_populates="portfolio_finding",
        cascade="all, delete-orphan",
    )

    __table_args__ = (

        CheckConstraint(
            "finding_type IN "
            "('similarity', 'potential_conflict', "
            "'repeated_risk', 'exposure_concentration')",
            name="check_portfolio_finding_type",
        ),

        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="check_portfolio_finding_severity",
        ),

        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="check_portfolio_finding_status",
        ),

        CheckConstraint(
            "assessment_status IN ('provisional', 'confirmed')",
            name="check_portfolio_finding_assessment_status",
        ),

        CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0 AND confidence <= 1)",
            name="check_portfolio_finding_confidence",
        ),

        Index(
            "ix_portfolio_findings_org_type_status",
            "organization_id",
            "finding_type",
            "status",
        ),

        Index(
            "uq_active_portfolio_finding_rule",
            "organization_id",
            "rule_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
    )


class PortfolioRiskFindingContract(Base):

    __tablename__ = "portfolio_risk_finding_contracts"

    portfolio_finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "portfolio_risk_findings.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    portfolio_finding = relationship(
        "PortfolioRiskFinding",
        back_populates="contract_links",
    )

    contract = relationship("Contract")

    __table_args__ = (
        Index(
            "ix_portfolio_finding_contract_contract",
            "contract_id",
        ),
    )


class PortfolioRiskFindingEvidence(Base):

    __tablename__ = "portfolio_risk_finding_evidence"

    portfolio_finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "portfolio_risk_findings.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    evidence_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        primary_key=True,
    )

    portfolio_finding = relationship(
        "PortfolioRiskFinding",
        back_populates="evidence_links",
    )

    evidence_record = relationship("EvidenceRecord")

    __table_args__ = (
        Index(
            "ix_portfolio_finding_evidence_record",
            "evidence_record_id",
        ),
    )