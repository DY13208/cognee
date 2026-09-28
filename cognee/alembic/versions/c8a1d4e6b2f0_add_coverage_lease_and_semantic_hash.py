"""Add coverage claim leases and proposal semantic hashes.

Revision ID: c8a1d4e6b2f0
Revises: b7e1c3a5d9f2
Create Date: 2026-09-28 18:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8a1d4e6b2f0"
down_revision: str | None = "b7e1c3a5d9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _names(inspector: sa.Inspector, table: str) -> set[str]:
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("teleology_proposals") and "semantic_context_hash" not in _names(
        inspector, "teleology_proposals"
    ):
        op.add_column(
            "teleology_proposals",
            sa.Column("semantic_context_hash", sa.String(length=64), nullable=True),
        )
    if inspector.has_table("teleology_analysis_run_items") and "lease_expires_at" not in _names(
        inspector, "teleology_analysis_run_items"
    ):
        op.add_column(
            "teleology_analysis_run_items",
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "lease_expires_at" in _names(inspector, "teleology_analysis_run_items"):
        op.drop_column("teleology_analysis_run_items", "lease_expires_at")
    if "semantic_context_hash" in _names(inspector, "teleology_proposals"):
        op.drop_column("teleology_proposals", "semantic_context_hash")
