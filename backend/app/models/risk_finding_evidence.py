from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RiskFindingEvidence(Base):

    __tablename__ = "risk_finding_evidence"

    risk_finding_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("risk_findings.id", ondelete="CASCADE"),
        primary_key=True
    )

    evidence_record_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        primary_key=True
    )

    risk_finding = relationship(
        "RiskFinding",
        back_populates="evidence_links"
    )

    evidence_record = relationship(
        "EvidenceRecord",
        back_populates="risk_finding_links"
    )