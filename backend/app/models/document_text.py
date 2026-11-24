import uuid

from datetime import datetime

from sqlalchemy import (
    Integer,
    Text,
    DateTime,
    ForeignKey,
    func
)

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid

from app.core.database import Base


class DocumentTextUnit(Base):

    __tablename__ = "document_text_units"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("contract_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    unit_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    extracted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )