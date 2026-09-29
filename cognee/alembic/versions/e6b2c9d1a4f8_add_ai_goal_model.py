"""Add the derived AI Goal Model tables.

Revision ID: e6b2c9d1a4f8
Revises: d4f7a1c8e2b0
Create Date: 2026-09-29 10:40:00.000000

These tables store proposals. They do not alter the company tree.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6b2c9d1a4f8"
down_revision: str | None = "d4f7a1c8e2b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_build_runs"):
        op.create_table(
            "teleology_build_runs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("dataset_id", sa.UUID(), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("batch_size", sa.Integer(), nullable=False),
            sa.Column("concurrency", sa.Integer(), nullable=False),
            sa.Column("max_sources", sa.Integer(), nullable=True),
            sa.Column("source_count", sa.Integer(), nullable=False),
            sa.Column("candidate_count", sa.Integer(), nullable=False),
            sa.Column("committed", sa.Integer(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teleology_build_runs_dataset",
            "teleology_build_runs",
            ["dataset_id", "status"],
        )
    if not inspector.has_table("teleology_goal_candidates"):
        op.create_table(
            "teleology_goal_candidates",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("dataset_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("source_node_ids", sa.Text(), nullable=False),
            sa.Column("evidence", sa.Text(), nullable=False),
            sa.Column("parent_candidate_id", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("generated_by", sa.String(length=64), nullable=False),
            sa.Column("semantic_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teleology_goal_candidates_dataset",
            "teleology_goal_candidates",
            ["dataset_id", "status"],
        )
        op.create_index(
            "ix_teleology_goal_candidates_hash",
            "teleology_goal_candidates",
            ["dataset_id", "semantic_hash"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_goal_candidates"):
        op.drop_table("teleology_goal_candidates")
    if inspector.has_table("teleology_build_runs"):
        op.drop_table("teleology_build_runs")
