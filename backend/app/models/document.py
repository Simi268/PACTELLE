import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    BigInteger,
    func
)

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.core.database import Base


class ContractDocument(Base):

    __tablename__ = "contract_documents"

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

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    file_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    processing_status: Mapped[str] = mapped_column(
        String(50),
        default="uploaded",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    contract = relationship(
        "Contract",
        back_populates="documents"
    )