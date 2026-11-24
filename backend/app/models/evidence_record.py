import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    Float,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class EvidenceRecord(Base):

    __tablename__ = "evidence_records"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_documents.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    clause_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_clauses.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    claim = Column(
        Text,
        nullable=False
    )

    evidence_type = Column(
        String(50),
        nullable=False
    )

    evidence_text = Column(
        Text,
        nullable=False
    )

    page_number = Column(
        Integer,
        nullable=True
    )

    char_start = Column(
        Integer,
        nullable=True
    )

    char_end = Column(
        Integer,
        nullable=True
    )

    extraction_method = Column(
        String(50),
        nullable=False,
        default="rule_based"
    )

    confidence = Column(
        Float,
        nullable=True
    )

    verification_status = Column(
        String(30),
        nullable=False,
        default="unverified"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    __table_args__ = (

        CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0 AND confidence <= 1)",
            name="check_evidence_confidence_range"
        ),

        CheckConstraint(
            "char_start IS NULL OR "
            "char_end IS NULL OR "
            "char_end >= char_start",
            name="check_evidence_character_range"
        ),

        CheckConstraint(
            "verification_status IN "
            "('unverified', 'verified', 'rejected')",
            name="ck_evidence_verification_status"
        ),

        Index(
            "ix_evidence_document_clause",
            "document_id",
            "clause_id"
        ),

        Index(
            "ix_evidence_records_clause_id",
            "clause_id"
        ),

        Index(
            "ix_evidence_records_document_id",
            "document_id"
        ),

        Index(
            "ix_evidence_records_evidence_type",
            "evidence_type"
        ),
    )

    document = relationship(
        "ContractDocument",
        back_populates="evidence_records"
    )

    clause = relationship(
        "ContractClause",
        back_populates="evidence_records"
    )

    risk_finding_links = relationship(
        "RiskFindingEvidence",
        back_populates="evidence_record",
        cascade="all, delete-orphan"
    )