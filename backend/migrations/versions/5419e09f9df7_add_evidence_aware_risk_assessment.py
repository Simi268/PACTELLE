"""Add evidence-aware risk assessment."""

from alembic import op
import sqlalchemy as sa


revision = "7b4d2a91c6e3"
down_revision = "c88a028df40b"

branch_labels = None
depends_on = None


def upgrade():

    op.add_column(
        "risk_findings",
        sa.Column(
            "assessment_status",
            sa.String(length=30),
            nullable=False,
            server_default="provisional"
        )
    )

    op.create_check_constraint(
        "ck_evidence_verification_status",
        "evidence_records",
        "verification_status IN ('unverified', 'verified', 'rejected')"
    )

    op.create_check_constraint(
        "check_risk_finding_assessment_status",
        "risk_findings",
        "assessment_status IN ('provisional', 'confirmed')"
    )


def downgrade():

    op.drop_constraint(
        "check_risk_finding_assessment_status",
        "risk_findings",
        type_="check"
    )

    op.drop_constraint(
        "ck_evidence_verification_status",
        "evidence_records",
        type_="check"
    )

    op.drop_column(
        "risk_findings",
        "assessment_status"
    )