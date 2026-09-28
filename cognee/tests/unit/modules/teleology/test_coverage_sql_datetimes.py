"""SQL coverage writes must hand PostgreSQL real datetime values."""

import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, event, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from cognee.infrastructure.databases.relational import Base
from cognee.modules.teleology.coverage_engine import CoverageEngine
from cognee.modules.teleology.coverage_models import (
    TeleologyAnalysisRunItemRecord,
    TeleologyAnalysisRunRecord,
    TeleologyAnalysisStateRecord,
)
from cognee.modules.teleology.coverage_store import SqlCoverageStore

DATASET = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
BOUND: list[tuple[str, datetime]] = []


class _GuardedStore(SqlCoverageStore):
    def __init__(self, factory) -> None:
        self._factory = factory

    async def _session(self):
        return self._factory()


def _reject_datetime_strings(session, _flush_context, _instances) -> None:
    pending = list(session.new) + list(session.dirty)
    for obj in pending:
        for attr in inspect(obj).mapper.column_attrs:
            column = attr.columns[0]
            value = getattr(obj, attr.key)
            if not isinstance(column.type, DateTime):
                continue
            if isinstance(value, str):
                raise TypeError(f"{attr.key} expected datetime, got str")
            if isinstance(value, datetime):
                BOUND.append((attr.key, value))


def _context(goal_id: str) -> dict:
    return {
        "dataset_id": DATASET,
        "goal": {"id": goal_id, "name": "目标", "description": "说明"},
        "note": "说明",
        "ancestors": [],
        "children": [],
        "entities": [],
        "documents": [],
        "child_evidence": [],
        "purposes": [],
        "constraints": [],
        "relations": [],
        "context_hash": "ctx",
    }


class _Sources:
    def __init__(self, explode: bool = False) -> None:
        self.explode = explode

    async def goal_page(self, _dataset_id, _user, offset, _limit):
        if self.explode:
            raise RuntimeError("scan failed")
        if offset:
            return [], 1
        return ["g"], 1

    async def context(self, _dataset_id, _user, goal_id):
        return _context(goal_id)

    async def analyze(self, _dataset_id, _user, goal_id):
        return {"id": "prop-" + goal_id, "items": [{"kind": "purpose", "name": "做成"}]}

    async def open_proposal(self, _dataset_id, _goal_id):
        return None

    async def mark_stale(self, _dataset_id, _user, _proposal):
        return None

    async def remember_semantic_hash(self, _dataset_id, _user, proposal, semantic_hash):
        proposal["semantic_context_hash"] = semantic_hash


@asynccontextmanager
async def _coverage_store():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + Path(path).as_posix(),
        connect_args={"check_same_thread": False},
    )
    tables = [
        TeleologyAnalysisStateRecord.__table__,
        TeleologyAnalysisRunRecord.__table__,
        TeleologyAnalysisRunItemRecord.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    BOUND.clear()
    event.listen(Session, "before_flush", _reject_datetime_strings)
    try:
        yield _GuardedStore(factory), factory
    finally:
        event.remove(Session, "before_flush", _reject_datetime_strings)
        await engine.dispose()
        os.remove(path)


def _assert_iso(value: str) -> None:
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None


async def _run_row(factory, run_id: str) -> TeleologyAnalysisRunRecord:
    async with factory() as session:
        return await session.get(TeleologyAnalysisRunRecord, UUID(run_id))


@pytest.mark.asyncio
async def test_sql_run_datetimes_round_trip_as_iso():
    async with _coverage_store() as (coverage, factory):
        engine = CoverageEngine(coverage, _Sources())
        created = await engine.start(DATASET, object(), mode="baseline", max_goals=1, wait=False)
        _assert_iso(created["started_at"])
        assert isinstance((await _run_row(factory, created["id"])).started_at, datetime)

        paused = await engine.pause(created["id"])
        _assert_iso(paused["paused_at"])
        assert isinstance((await _run_row(factory, created["id"])).paused_at, datetime)

        resumed = await engine.resume(created["id"], DATASET, object(), wait=False)
        assert resumed["paused_at"] is None
        assert (await _run_row(factory, created["id"])).paused_at is None

        cancelled = await engine.cancel(created["id"])
        assert cancelled["status"] == "cancelled"
        _assert_iso(cancelled["completed_at"])
        assert isinstance((await _run_row(factory, created["id"])).completed_at, datetime)


@pytest.mark.asyncio
async def test_sql_store_converts_iso_strings_before_flush():
    async with _coverage_store() as (coverage, factory):
        created = await coverage.create_run(
            {
                "id": str(uuid4()),
                "dataset_id": DATASET,
                "mode": "baseline",
                "status": "running",
                "started_at": "2026-09-28T10:00:00+00:00",
            }
        )
        await coverage.update_run(created["id"], paused_at="2026-09-28T11:00:00+00:00")
        await coverage.upsert_state(
            {
                "dataset_id": DATASET,
                "goal_id": "g",
                "status": "clean",
                "last_analyzed_at": "2026-09-28T12:00:00+00:00",
                "last_success_at": "2026-09-28T12:00:00+00:00",
            }
        )
        row = await _run_row(factory, created["id"])
        assert isinstance(row.started_at, datetime)
        assert isinstance(row.paused_at, datetime)
        async with factory() as session:
            state = (
                await session.execute(
                    select(TeleologyAnalysisStateRecord).where(
                        TeleologyAnalysisStateRecord.goal_id == "g"
                    )
                )
            ).scalar_one()
            assert isinstance(state.last_analyzed_at, datetime)
            assert isinstance(state.last_success_at, datetime)


@pytest.mark.asyncio
async def test_sql_completion_and_failure_write_datetimes():
    async with _coverage_store() as (coverage, factory):
        engine = CoverageEngine(coverage, _Sources())
        finished = await engine.start(
            DATASET, object(), mode="baseline", max_goals=1, concurrency=1, wait=True
        )
        assert finished["status"] == "completed"
        assert isinstance(finished["completed_at"], str) and finished["completed_at"]
        assert any(key == "completed_at" and value.tzinfo for key, value in BOUND)
        queued = await coverage.list_items(finished["id"])
        await engine._finish_success(
            finished["id"],
            DATASET,
            "g",
            {"id": queued[0]["id"]},
            _context("g"),
            "hash",
            {"id": "prop-g", "items": [{"kind": "purpose", "name": "做成"}]},
            {"status": "queued", "goal_id": "g"},
        )
        state = await engine.store.get_state(DATASET, "g")
        assert isinstance(state["last_analyzed_at"], str) and state["last_analyzed_at"]
        assert isinstance(state["last_success_at"], str) and state["last_success_at"]
        assert any(key == "last_analyzed_at" and value.tzinfo for key, value in BOUND)
        assert any(key == "last_success_at" and value.tzinfo for key, value in BOUND)
        async with factory() as session:
            saved = (
                await session.execute(
                    select(TeleologyAnalysisStateRecord).where(
                        TeleologyAnalysisStateRecord.goal_id == "g"
                    )
                )
            ).scalar_one()
        assert saved.last_analyzed_at is not None
        assert saved.last_success_at is not None

        failing = CoverageEngine(_GuardedStore(factory), _Sources(explode=True))
        broken = await failing.start(DATASET, object(), mode="baseline", wait=False)
        await failing.drive(broken["id"], DATASET, object())
        saved_run = await failing.store.get_run(broken["id"])
        assert saved_run["status"] == "failed"
        assert isinstance(saved_run["completed_at"], str) and saved_run["completed_at"]
        assert any(key == "completed_at" and value.tzinfo for key, value in BOUND)
