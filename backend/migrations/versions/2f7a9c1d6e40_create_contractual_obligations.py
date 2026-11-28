"""create contractual obligation lifecycle tables

Revision ID: 2f7a9c1d6e40
Revises: 94622ed81a06
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2f7a9c1d6e40"
down_revision = "94622ed81a06"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contractual_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("obligation_type", sa.String(length=80), nullable=False),
        sa.Column("obligation_family", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("duration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="open", nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("completion_evidence_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evidence_record_id", name="uq_contractual_obligation_evidence"),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'completed', 'waived')", name="ck_contractual_obligation_status"),
        sa.CheckConstraint("verification_status IN ('unverified', 'verified', 'rejected')", name="ck_contractual_obligation_verification_status"),
    )
    op.create_index("ix_contractual_obligations_org_status", "contractual_obligations", ["organization_id", "status"])
    op.create_index("ix_contractual_obligations_org_due_date", "contractual_obligations", ["organization_id", "due_date"])
    op.create_index("ix_contractual_obligations_contract", "contractual_obligations", ["contract_id"])
    op.create_index("ix_contractual_obligations_assignee", "contractual_obligations", ["assigned_to_user_id"])

    op.create_table(
        "contractual_obligation_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contractual_obligations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_contractual_obligation_audits_obligation_created",
        "contractual_obligation_audits",
        ["obligation_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_contractual_obligation_audits_obligation_created", table_name="contractual_obligation_audits")
    op.drop_table("contractual_obligation_audits")
    op.drop_index("ix_contractual_obligations_assignee", table_name="contractual_obligations")
    op.drop_index("ix_contractual_obligations_contract", table_name="contractual_obligations")
    op.drop_index("ix_contractual_obligations_org_due_date", table_name="contractual_obligations")
    op.drop_index("ix_contractual_obligations_org_status", table_name="contractual_obligations")
    op.drop_table("contractual_obligations")
