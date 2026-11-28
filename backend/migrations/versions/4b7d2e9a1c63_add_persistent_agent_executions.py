"""Add persistent agent execution records and workflow checkpoints."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "4b7d2e9a1c63"
down_revision = "c4e91a7b2d60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_executions",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("checkpoint_agent", sa.String(length=40), nullable=True),
        sa.Column("next_agent_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("review_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'needs_ocr', 'superseded', 'failed', 'review_required', 'cancelled')",
            name="ck_agent_execution_status",
        ),
        sa.CheckConstraint("next_agent_index >= 0", name="ck_agent_execution_next_index"),
        sa.CheckConstraint("resume_count >= 0", name="ck_agent_execution_resume_count"),
        sa.CheckConstraint("version >= 1", name="ck_agent_execution_version"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_request_id"], ["review_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("execution_id"),
    )
    op.create_index(
        "ix_agent_executions_org_status_created",
        "agent_executions",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_agent_executions_review_request",
        "agent_executions",
        ["review_request_id"],
    )


def downgrade():
    op.drop_index("ix_agent_executions_review_request", table_name="agent_executions")
    op.drop_index("ix_agent_executions_org_status_created", table_name="agent_executions")
    op.drop_table("agent_executions")
