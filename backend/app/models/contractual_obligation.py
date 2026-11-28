import uuid

from sqlalchemy import (
    Column, String, Text, Date, DateTime, ForeignKey, UniqueConstraint,
    CheckConstraint, Index, Float, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class ContractualObligation(Base):
    __tablename__ = "contractual_obligations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    evidence_record_id = Column(UUID(as_uuid=True), ForeignKey("evidence_records.id", ondelete="CASCADE"), nullable=False)
    obligation_type = Column(String(80), nullable=False)
    obligation_family = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    claim = Column(Text, nullable=False)
    original_text = Column(Text, nullable=False)
    duration = Column(JSONB, nullable=True)
    verification_status = Column(String(30), nullable=False)
    confidence = Column(Float, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="open", server_default="open")
    assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_note = Column(Text, nullable=True)
    completion_evidence_record_id = Column(UUID(as_uuid=True), ForeignKey("evidence_records.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    waived_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    evidence_record = relationship("EvidenceRecord", foreign_keys=[evidence_record_id])
    completion_evidence = relationship("EvidenceRecord", foreign_keys=[completion_evidence_record_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    audit_entries = relationship(
        "ContractualObligationAudit",
        back_populates="obligation",
        cascade="all, delete-orphan",
        order_by="ContractualObligationAudit.created_at",
    )

    __table_args__ = (
        UniqueConstraint("evidence_record_id", name="uq_contractual_obligation_evidence"),
        CheckConstraint("status IN ('open', 'in_progress', 'completed', 'waived')", name="ck_contractual_obligation_status"),
        CheckConstraint("verification_status IN ('unverified', 'verified', 'rejected')", name="ck_contractual_obligation_verification_status"),
        Index("ix_contractual_obligations_org_status", "organization_id", "status"),
        Index("ix_contractual_obligations_org_due_date", "organization_id", "due_date"),
        Index("ix_contractual_obligations_contract", "contract_id"),
        Index("ix_contractual_obligations_assignee", "assigned_to_user_id"),
    )


class ContractualObligationAudit(Base):
    __tablename__ = "contractual_obligation_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obligation_id = Column(UUID(as_uuid=True), ForeignKey("contractual_obligations.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False)
    previous_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    obligation = relationship("ContractualObligation", back_populates="audit_entries")
    actor = relationship("User")

    __table_args__ = (
        Index("ix_contractual_obligation_audits_obligation_created", "obligation_id", "created_at"),
    )
