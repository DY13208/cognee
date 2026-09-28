"""Relational tables for teleology coverage. The queue lives here, not in process memory."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import UUID, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from cognee.infrastructure.databases.relational import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TeleologyAnalysisStateRecord(Base):
    __tablename__ = "teleology_analysis_state"

    id = Column(UUID, primary_key=True, default=uuid4)
    dataset_id = Column(UUID, nullable=False)
    goal_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="never_analyzed")
    semantic_context_hash = Column(String(64), nullable=True)
    last_context_hash = Column(String(64), nullable=True)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_proposal_id = Column(String(64), nullable=True)
    last_run_id = Column(String(64), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    model_version = Column(String(128), nullable=True)
    dirty_reason = Column(String(128), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("dataset_id", "goal_id", name="uq_teleology_analysis_state_goal"),
        Index("ix_teleology_analysis_state_status", "dataset_id", "status"),
    )


class TeleologyAnalysisRunRecord(Base):
    __tablename__ = "teleology_analysis_runs"

    id = Column(UUID, primary_key=True, default=uuid4)
    dataset_id = Column(UUID, nullable=False)
    mode = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    batch_size = Column(Integer, nullable=False, default=20)
    concurrency = Column(Integer, nullable=False, default=3)
    max_goals = Column(Integer, nullable=True)
    token_budget = Column(Integer, nullable=True)
    used_input_tokens = Column(Integer, nullable=True)
    used_output_tokens = Column(Integer, nullable=True)
    total_goals = Column(Integer, nullable=False, default=0)
    eligible_goals = Column(Integer, nullable=False, default=0)
    queued_goals = Column(Integer, nullable=False, default=0)
    processed_goals = Column(Integer, nullable=False, default=0)
    skipped_goals = Column(Integer, nullable=False, default=0)
    proposal_goals = Column(Integer, nullable=False, default=0)
    no_change_goals = Column(Integer, nullable=False, default=0)
    no_context_goals = Column(Integer, nullable=False, default=0)
    failed_goals = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_teleology_analysis_runs_dataset", "dataset_id", "status"),)


class TeleologyAnalysisRunItemRecord(Base):
    __tablename__ = "teleology_analysis_run_items"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, nullable=False)
    goal_id = Column(String(64), nullable=False)
    priority = Column(Integer, nullable=False, default=3)
    status = Column(String(32), nullable=False, default="pending")
    semantic_context_hash = Column(String(64), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    proposal_id = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    action = Column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "goal_id", name="uq_teleology_analysis_run_item"),
        Index("ix_teleology_analysis_run_items_status", "run_id", "status", "priority"),
    )
