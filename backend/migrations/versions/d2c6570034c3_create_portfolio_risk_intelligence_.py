"""create portfolio risk intelligence tables

Revision ID: d2c6570034c3
Revises: b71e9c42a613
Create Date: 2026-11-26 10:44:24.300869

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d2c6570034c3"

down_revision: Union[str, Sequence[str], None] = "b71e9c42a613"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "portfolio_risk_findings",

        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "organization_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "finding_type",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "severity",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            server_default="open",
            nullable=False,
        ),

        sa.Column(
            "assessment_status",
            sa.String(length=30),
            server_default="provisional",
            nullable=False,
        ),

        sa.Column(
            "detection_method",
            sa.String(length=50),
            server_default="rule_based",
            nullable=False,
        ),

        sa.Column(
            "rule_id",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "rule_version",
            sa.String(length=30),
            server_default="1.0",
            nullable=False,
        ),

        sa.Column(
            "confidence",
            sa.Float(),
            nullable=True,
        ),

        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.CheckConstraint(
            "finding_type IN "
            "('similarity', 'potential_conflict', "
            "'repeated_risk', 'exposure_concentration')",
            name="check_portfolio_finding_type",
        ),

        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="check_portfolio_finding_severity",
        ),

        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="check_portfolio_finding_status",
        ),

        sa.CheckConstraint(
            "assessment_status IN ('provisional', 'confirmed')",
            name="check_portfolio_finding_assessment_status",
        ),

        sa.CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0 AND confidence <= 1)",
            name="check_portfolio_finding_confidence",
        ),

        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_portfolio_findings_org_type_status",
        "portfolio_risk_findings",
        ["organization_id", "finding_type", "status"],
        unique=False,
    )

    op.create_index(
        "ix_portfolio_risk_findings_finding_type",
        "portfolio_risk_findings",
        ["finding_type"],
        unique=False,
    )

    op.create_index(
        "uq_active_portfolio_finding_rule",
        "portfolio_risk_findings",
        ["organization_id", "rule_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )

    op.create_table(
        "portfolio_risk_finding_contracts",

        sa.Column(
            "portfolio_finding_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "contract_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["portfolio_finding_id"],
            ["portfolio_risk_findings.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "portfolio_finding_id",
            "contract_id",
        ),
    )

    op.create_index(
        "ix_portfolio_finding_contract_contract",
        "portfolio_risk_finding_contracts",
        ["contract_id"],
        unique=False,
    )

    op.create_table(
        "portfolio_risk_finding_evidence",

        sa.Column(
            "portfolio_finding_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.Column(
            "evidence_record_id",
            sa.Uuid(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["portfolio_finding_id"],
            ["portfolio_risk_findings.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["evidence_record_id"],
            ["evidence_records.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "portfolio_finding_id",
            "evidence_record_id",
        ),
    )

    op.create_index(
        "ix_portfolio_finding_evidence_record",
        "portfolio_risk_finding_evidence",
        ["evidence_record_id"],
        unique=False,
    )


def downgrade() -> None:

    op.drop_index(
        "ix_portfolio_finding_evidence_record",
        table_name="portfolio_risk_finding_evidence",
    )

    op.drop_table(
        "portfolio_risk_finding_evidence",
    )

    op.drop_index(
        "ix_portfolio_finding_contract_contract",
        table_name="portfolio_risk_finding_contracts",
    )

    op.drop_table(
        "portfolio_risk_finding_contracts",
    )

    op.drop_index(
        "uq_active_portfolio_finding_rule",
        table_name="portfolio_risk_findings",
        postgresql_where=sa.text("status <> 'resolved'"),
    )

    op.drop_index(
        "ix_portfolio_risk_findings_finding_type",
        table_name="portfolio_risk_findings",
    )

    op.drop_index(
        "ix_portfolio_findings_org_type_status",
        table_name="portfolio_risk_findings",
    )

    op.drop_table(
        "portfolio_risk_findings",
    )