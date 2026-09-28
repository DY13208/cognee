"""Relational storage for teleology proposals. JSON files remain a fallback."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import UUID, Column, DateTime, Float, Index, String, Text

from cognee.infrastructure.databases.relational import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TeleologyProposalRecord(Base):
    __tablename__ = "teleology_proposals"

    id = Column(UUID, primary_key=True, default=uuid4)
    dataset_id = Column(UUID, nullable=False)
    source_goal_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="open")
    generated_by = Column(String(64), nullable=False)
    run_id = Column(String(64), nullable=True)
    source_revision = Column(String(128), nullable=True)
    context_hash = Column(String(64), nullable=True)
    semantic_context_hash = Column(String(64), nullable=True)
    analysis_summary = Column(Text, nullable=True)
    user_id = Column(UUID, nullable=True)
    payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    committed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_teleology_proposals_dataset", "dataset_id", "status"),
        Index("ix_teleology_proposals_goal", "dataset_id", "source_goal_id"),
    )


class TeleologyProposalItemRecord(Base):
    __tablename__ = "teleology_proposal_items"

    id = Column(UUID, primary_key=True, default=uuid4)
    proposal_id = Column(UUID, nullable=False)
    kind = Column(String(32), nullable=False)
    name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String(64), nullable=True)
    target = Column(String(64), nullable=True)
    relationship = Column(String(32), nullable=True)
    confidence = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    evidence_node_ids = Column(Text, nullable=True)
    source_goal_ids = Column(Text, nullable=True)
    review_status = Column(String(32), nullable=False, default="proposed")
    committed_node_id = Column(String(64), nullable=True)
    committed_edge_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (Index("ix_teleology_proposal_items_proposal", "proposal_id"),)
