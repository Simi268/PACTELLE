"""Merge the three existing PACTELLE migration heads.

This is a graph-only merge. It intentionally performs no schema operations.
"""

revision = "c4e91a7b2d60"
down_revision = (
    "7b4d2a91c6e3",
    "b71e9c42a613",
    "f31c8a72d904",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
