"""add deadline date to risk findings

Revision ID: eec0c211eb41
Revises: 9f2c89efbb58
Create Date: 2026-11-24 09:54:03.524060

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "eec0c211eb41"
down_revision: Union[str, Sequence[str], None] = "9f2c89efbb58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deadline_date to risk_findings."""

    op.add_column(
        "risk_findings",
        sa.Column(
            "deadline_date",
            sa.Date(),
            nullable=True
        )
    )


def downgrade() -> None:
    """Remove deadline_date from risk_findings."""

    op.drop_column(
        "risk_findings",
        "deadline_date"
    )