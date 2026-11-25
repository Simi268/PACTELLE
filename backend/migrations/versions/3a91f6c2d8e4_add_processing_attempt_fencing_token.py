"""add document processing attempt fencing token

Revision ID: 3a91f6c2d8e4
Revises: 0d21204ecbd9
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3a91f6c2d8e4"
down_revision: Union[str, Sequence[str], None] = "0d21204ecbd9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_documents",
        sa.Column("processing_attempt_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_contract_documents_processing_attempt_id",
        "contract_documents",
        ["processing_attempt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contract_documents_processing_attempt_id",
        table_name="contract_documents",
    )
    op.drop_column("contract_documents", "processing_attempt_id")
