from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b71e9c42a613"

down_revision = "3a91f6c2d8e4"

branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "risk_events",

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "risk_finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "risk_findings.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),

        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contracts.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="system",
        ),

        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),

        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "previous_state",
            postgresql.JSONB(),
            nullable=True,
        ),

        sa.Column(
            "new_state",
            postgresql.JSONB(),
            nullable=True,
        ),

        sa.Column(
            "evidence_snapshot",
            postgresql.JSONB(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_risk_events_risk_finding_id",
        "risk_events",
        ["risk_finding_id"],
    )

    op.create_index(
        "ix_risk_events_contract_id",
        "risk_events",
        ["contract_id"],
    )

    op.create_index(
        "ix_risk_events_event_type",
        "risk_events",
        ["event_type"],
    )

    op.create_index(
        "ix_risk_events_contract_created",
        "risk_events",
        ["contract_id", "created_at"],
    )

    op.create_index(
        "ix_risk_events_finding_created",
        "risk_events",
        ["risk_finding_id", "created_at"],
    )


def downgrade():

    op.drop_table("risk_events")