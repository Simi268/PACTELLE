import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

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
        ForeignKey("contract_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    clause_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contract_clauses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # What PACTELLE has identified
    claim = Column(Text, nullable=False)

    # Type of information represented by the claim
    evidence_type = Column(
        String(50),
        nullable=False,
        index=True
    )

    # Exact text from the original document
    evidence_text = Column(Text, nullable=False)

    # Source location
    page_number = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)

    # How this evidence was extracted
    extraction_method = Column(
        String(50),
        nullable=False,
        default="rule_based"
    )

    # Confidence is optional until we have a calibrated scoring method
    confidence = Column(Float, nullable=True)

    # Human verification status
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
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="check_evidence_confidence_range"
        ),
        CheckConstraint(
            "char_start IS NULL OR char_end IS NULL OR char_end >= char_start",
            name="check_evidence_character_range"
        ),
        Index(
            "ix_evidence_document_clause",
            "document_id",
            "clause_id"
        ),
    )