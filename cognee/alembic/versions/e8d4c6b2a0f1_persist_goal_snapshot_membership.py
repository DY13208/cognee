"""Persist Goal Model snapshot membership separately from review status.

Revision ID: e8d4c6b2a0f1
Revises: e7c3d5f9a1b2
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8d4c6b2a0f1"
down_revision: str | None = "e7c3d5f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("teleology_goal_candidates"):
        return
    columns = {column["name"] for column in inspector.get_columns("teleology_goal_candidates")}
    if "outside_current_snapshot" in columns:
        return
    op.add_column(
        "teleology_goal_candidates",
        sa.Column(
            "outside_current_snapshot", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    connection = op.get_bind()
    candidates = sa.table(
        "teleology_goal_candidates",
        sa.column("id", sa.String()),
        sa.column("status", sa.String()),
        sa.column("run_id", sa.String()),
        sa.column("outside_current_snapshot", sa.Boolean()),
    )
    runs = sa.table(
        "teleology_build_runs", sa.column("id", sa.UUID()), sa.column("payload", sa.Text())
    )
    outside_by_run = {}
    if inspector.has_table("teleology_build_runs"):
        for run_id, raw_payload in connection.execute(sa.select(runs.c.id, runs.c.payload)):
            try:
                payload = json.loads(raw_payload or "{}")
            except (TypeError, ValueError):
                continue
            outside_by_run[str(run_id)] = {
                str(goal.get("id"))
                for goal in payload.get("candidates") or []
                if isinstance(goal, dict)
                and (
                    goal.get("outside_current_snapshot") or goal.get("status") == "legacy_confirmed"
                )
            }
    for goal_id, run_id in connection.execute(sa.select(candidates.c.id, candidates.c.run_id)):
        if goal_id in outside_by_run.get(str(run_id), set()):
            connection.execute(
                candidates.update()
                .where(candidates.c.id == goal_id)
                .values(outside_current_snapshot=True)
            )
    connection.execute(
        candidates.update()
        .where(candidates.c.status == "legacy_confirmed")
        .values(outside_current_snapshot=True)
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_goal_candidates") and any(
        column["name"] == "outside_current_snapshot"
        for column in inspector.get_columns("teleology_goal_candidates")
    ):
        op.drop_column("teleology_goal_candidates", "outside_current_snapshot")
