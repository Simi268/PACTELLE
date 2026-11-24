import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
    Uuid
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContractClause(Base):

    __tablename__ = "contract_clauses"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "clause_number",
            name="uq_document_clause_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "contract_documents.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    clause_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    clause_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    source_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    char_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    char_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    extraction_method: Mapped[str] = mapped_column(
        String(50),
        default="rule_based",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    evidence_records = relationship(
        "EvidenceRecord",
        back_populates="clause",
        cascade="all, delete-orphan"
    )