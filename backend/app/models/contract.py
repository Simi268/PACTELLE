import uuid

from datetime import datetime, date

from sqlalchemy import (
    String,
    Date,
    DateTime,
    ForeignKey,
    func
)

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.core.database import Base


class Contract(Base):

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    contract_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False
    )

    effective_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    expiration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    organization = relationship(
        "Organization",
        back_populates="contracts"
    )