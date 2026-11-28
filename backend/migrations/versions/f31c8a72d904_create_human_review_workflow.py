"""Create organization-scoped human review requests and audit history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f31c8a72d904"
down_revision = "2f7a9c1d6e40"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_type", sa.String(length=40), nullable=False),
        sa.Column("subject_type", sa.String(length=50), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_interpretation", sa.Text(), nullable=True),
        sa.Column("evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "review_type IN ('evidence_verification', 'interpretation', 'legal_review', 'action_approval')",
            name="ck_review_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'clarification_requested', 'cancelled')",
            name="ck_review_request_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_requests_org_status_created", "review_requests", ["organization_id", "status", "created_at"])
    op.create_index("ix_review_requests_execution", "review_requests", ["execution_id"])
    op.create_index("ix_review_requests_assignee_status", "review_requests", ["assigned_to_user_id", "status"])

    op.create_table(
        "review_request_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_request_id"], ["review_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_request_audits_request_created",
        "review_request_audits",
        ["review_request_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_review_request_audits_request_created", table_name="review_request_audits")
    op.drop_table("review_request_audits")
    op.drop_index("ix_review_requests_assignee_status", table_name="review_requests")
    op.drop_index("ix_review_requests_execution", table_name="review_requests")
    op.drop_index("ix_review_requests_org_status_created", table_name="review_requests")
    op.drop_table("review_requests")
