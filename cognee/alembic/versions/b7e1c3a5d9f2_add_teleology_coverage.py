"""Add teleology coverage state, runs, and queue items.

Revision ID: b7e1c3a5d9f2
Revises: a9c1e3f5b7d2
Create Date: 2026-09-28 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c3a5d9f2"
down_revision: str | None = "a9c1e3f5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_analysis_state"):
        op.create_table(
            "teleology_analysis_state",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("dataset_id", sa.UUID(), nullable=False),
            sa.Column("goal_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("semantic_context_hash", sa.String(length=64), nullable=True),
            sa.Column("last_context_hash", sa.String(length=64), nullable=True),
            sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_proposal_id", sa.String(length=64), nullable=True),
            sa.Column("last_run_id", sa.String(length=64), nullable=True),
            sa.Column("prompt_version", sa.String(length=64), nullable=True),
            sa.Column("model_version", sa.String(length=128), nullable=True),
            sa.Column("dirty_reason", sa.String(length=128), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dataset_id", "goal_id", name="uq_teleology_analysis_state_goal"),
        )
        op.create_index(
            "ix_teleology_analysis_state_status",
            "teleology_analysis_state",
            ["dataset_id", "status"],
        )
    if not inspector.has_table("teleology_analysis_runs"):
        op.create_table(
            "teleology_analysis_runs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("dataset_id", sa.UUID(), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("batch_size", sa.Integer(), nullable=False),
            sa.Column("concurrency", sa.Integer(), nullable=False),
            sa.Column("max_goals", sa.Integer(), nullable=True),
            sa.Column("token_budget", sa.Integer(), nullable=True),
            sa.Column("used_input_tokens", sa.Integer(), nullable=True),
            sa.Column("used_output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_goals", sa.Integer(), nullable=False),
            sa.Column("eligible_goals", sa.Integer(), nullable=False),
            sa.Column("queued_goals", sa.Integer(), nullable=False),
            sa.Column("processed_goals", sa.Integer(), nullable=False),
            sa.Column("skipped_goals", sa.Integer(), nullable=False),
            sa.Column("proposal_goals", sa.Integer(), nullable=False),
            sa.Column("no_change_goals", sa.Integer(), nullable=False),
            sa.Column("no_context_goals", sa.Integer(), nullable=False),
            sa.Column("failed_goals", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teleology_analysis_runs_dataset",
            "teleology_analysis_runs",
            ["dataset_id", "status"],
        )
    if not inspector.has_table("teleology_analysis_run_items"):
        op.create_table(
            "teleology_analysis_run_items",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("run_id", sa.UUID(), nullable=False),
            sa.Column("goal_id", sa.String(length=64), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("semantic_context_hash", sa.String(length=64), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("proposal_id", sa.String(length=64), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=32), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "goal_id", name="uq_teleology_analysis_run_item"),
        )
        op.create_index(
            "ix_teleology_analysis_run_items_status",
            "teleology_analysis_run_items",
            ["run_id", "status", "priority"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_analysis_run_items"):
        op.drop_table("teleology_analysis_run_items")
    if inspector.has_table("teleology_analysis_runs"):
        op.drop_table("teleology_analysis_runs")
    if inspector.has_table("teleology_analysis_state"):
        op.drop_table("teleology_analysis_state")
