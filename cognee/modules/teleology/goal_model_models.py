"""Relational shape of the derived AI Goal Model.

The company tree is not stored here. Applying the migration does not read or
write a dataset. The build runtime keeps proposals in the process store until
this schema is migrated.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import UUID, Column, DateTime, Float, Index, Integer, String, Text

from cognee.infrastructure.databases.relational import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TeleologyBuildRunRecord(Base):
    __tablename__ = "teleology_build_runs"

    id = Column(UUID, primary_key=True, default=uuid4)
    dataset_id = Column(UUID, nullable=False)
    mode = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="discovering")
    batch_size = Column(Integer, nullable=False, default=20)
    concurrency = Column(Integer, nullable=False, default=1)
    max_sources = Column(Integer, nullable=True)
    source_count = Column(Integer, nullable=False, default=0)
    candidate_count = Column(Integer, nullable=False, default=0)
    committed = Column(Integer, nullable=False, default=0)
    payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_teleology_build_runs_dataset", "dataset_id", "status"),)


class TeleologyGoalCandidateRecord(Base):
    __tablename__ = "teleology_goal_candidates"

    id = Column(String(64), primary_key=True)
    dataset_id = Column(UUID, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    source_node_ids = Column(Text, nullable=False, default="[]")
    evidence = Column(Text, nullable=False, default="[]")
    parent_candidate_id = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="proposed")
    run_id = Column(String(64), nullable=False)
    generated_by = Column(String(64), nullable=False)
    semantic_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_teleology_goal_candidates_dataset", "dataset_id", "status"),
        Index("ix_teleology_goal_candidates_hash", "dataset_id", "semantic_hash"),
    )
