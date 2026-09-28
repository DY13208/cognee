"""Add teleology proposal tables.

Revision ID: a9c1e3f5b7d2
Revises: e8b4d2c6a901
Create Date: 2026-09-28 16:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c1e3f5b7d2"
down_revision: Union[str, None] = "e8b4d2c6a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_proposals"):
        op.create_table(
            "teleology_proposals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("dataset_id", sa.UUID(), nullable=False),
            sa.Column("source_goal_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("generated_by", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("source_revision", sa.String(length=128), nullable=True),
            sa.Column("context_hash", sa.String(length=64), nullable=True),
            sa.Column("analysis_summary", sa.Text(), nullable=True),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teleology_proposals_dataset",
            "teleology_proposals",
            ["dataset_id", "status"],
        )
        op.create_index(
            "ix_teleology_proposals_goal",
            "teleology_proposals",
            ["dataset_id", "source_goal_id"],
        )
    if not inspector.has_table("teleology_proposal_items"):
        op.create_table(
            "teleology_proposal_items",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("proposal_id", sa.UUID(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("name", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("target", sa.String(length=64), nullable=True),
            sa.Column("relationship", sa.String(length=32), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("evidence_node_ids", sa.Text(), nullable=True),
            sa.Column("source_goal_ids", sa.Text(), nullable=True),
            sa.Column("review_status", sa.String(length=32), nullable=False),
            sa.Column("committed_node_id", sa.String(length=64), nullable=True),
            sa.Column("committed_edge_key", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teleology_proposal_items_proposal",
            "teleology_proposal_items",
            ["proposal_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_proposal_items"):
        op.drop_table("teleology_proposal_items")
    if inspector.has_table("teleology_proposals"):
        op.drop_table("teleology_proposals")
