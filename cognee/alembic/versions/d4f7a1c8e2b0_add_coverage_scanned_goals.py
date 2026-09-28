"""Add scanned_goals so a coverage run can report progress while it scans.

Revision ID: d4f7a1c8e2b0
Revises: c8a1d4e6b2f0
Create Date: 2026-09-28 18:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7a1c8e2b0"
down_revision: str | None = "c8a1d4e6b2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _names(inspector: sa.Inspector, table: str) -> set[str]:
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_analysis_runs") and "scanned_goals" not in _names(
        inspector, "teleology_analysis_runs"
    ):
        op.add_column(
            "teleology_analysis_runs",
            sa.Column("scanned_goals", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "scanned_goals" in _names(inspector, "teleology_analysis_runs"):
        op.drop_column("teleology_analysis_runs", "scanned_goals")
