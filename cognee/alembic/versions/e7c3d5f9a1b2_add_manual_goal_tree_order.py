"""Persist manual parent and sibling order for derived goals.

Revision ID: e7c3d5f9a1b2
Revises: e6b2c9d1a4f8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c3d5f9a1b2"
down_revision: str | None = "e6b2c9d1a4f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_goal_candidates"):
        return
    columns = {column["name"] for column in inspector.get_columns("teleology_goal_candidates")}
    if "parent_override" not in columns:
        op.add_column(
            "teleology_goal_candidates",
            sa.Column("parent_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "sort_order" not in columns:
        op.add_column(
            "teleology_goal_candidates", sa.Column("sort_order", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_goal_candidates"):
        return
    columns = {column["name"] for column in inspector.get_columns("teleology_goal_candidates")}
    if "sort_order" in columns:
        op.drop_column("teleology_goal_candidates", "sort_order")
    if "parent_override" in columns:
        op.drop_column("teleology_goal_candidates", "parent_override")
