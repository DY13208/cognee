from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from cognee.modules.teleology.goal_model import GoalBuildError
from cognee.modules.teleology.goal_model_models import (
    TeleologyBuildRunRecord,
    TeleologyGoalCandidateRecord,
)
from cognee.modules.teleology.goal_store import MemoryGoalRunStore, SqlGoalModelStore
from cognee.modules.teleology.goal_tree import move_candidate, ordered_candidates


def candidates():
    return [
        {"id": "root", "name": "Root", "parent_candidate_id": None, "status": "confirmed"},
        {"id": "a", "name": "A", "parent_candidate_id": "root", "status": "confirmed"},
        {"id": "b", "name": "B", "parent_candidate_id": "root", "status": "proposed"},
        {"id": "c", "name": "C", "parent_candidate_id": None, "status": "confirmed"},
    ]


def test_reorders_siblings_and_reparents_without_changing_review_status():
    goals = candidates()
    move_candidate(goals, "b", "a", "before")
    siblings = [
        goal["id"] for goal in ordered_candidates(goals) if goal["parent_candidate_id"] == "root"
    ]
    assert siblings == ["b", "a"]

    result = move_candidate(goals, "a", "c", "inside")
    assert result["parent_changed"] is True
    assert next(goal for goal in goals if goal["id"] == "a")["status"] == "confirmed"
    assert next(goal for goal in goals if goal["id"] == "a")["parent_override"] is True


def test_rejects_cycles_and_missing_targets():
    goals = candidates()
    with pytest.raises(GoalBuildError, match="cycle"):
        move_candidate(goals, "root", "a", "inside")
    with pytest.raises(GoalBuildError, match="not available"):
        move_candidate(goals, "a", "missing", "inside")


@pytest.mark.asyncio
async def test_memory_store_keeps_manual_tree_edits_across_rebuild():
    store = MemoryGoalRunStore()
    first = {
        "run_id": "run-1",
        "dataset_id": "dataset-1",
        "status": "completed",
        "candidates": candidates(),
    }
    await store.save_result(first)
    await store.move_candidate("dataset-1", "a", "c", "inside")
    await store.move_candidate("dataset-1", "b", "root", "before")
    updated = {**first, "run_id": "run-2", "candidates": candidates()}
    await store.save_result(updated)

    view = await store.get_dataset("dataset-1")
    assert view is not None
    by_id = {goal["id"]: goal for goal in view["candidates"]}
    assert by_id["a"]["parent_candidate_id"] == "c"
    assert by_id["a"]["parent_override"] is True
    assert [goal["id"] for goal in view["hierarchy"] if goal["parent_candidate_id"] is None] == [
        "b",
        "root",
        "c",
    ]


@pytest.mark.asyncio
async def test_sql_store_reloads_manual_order_and_keeps_it_after_rebuild():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def _create(sync_conn):
        TeleologyBuildRunRecord.__table__.create(sync_conn)
        TeleologyGoalCandidateRecord.__table__.create(sync_conn)

    async with engine.begin() as connection:
        await connection.run_sync(_create)
    store = SqlGoalModelStore(async_sessionmaker(engine, expire_on_commit=False))
    dataset_id = str(uuid4())
    first_run = str(uuid4())
    first = {
        "run_id": first_run,
        "dataset_id": dataset_id,
        "status": "completed",
        "mode": "orchestrated",
        "candidates": candidates(),
    }
    await store.save_result(first)
    await store.move_candidate(dataset_id, "a", "c", "inside")
    await store.move_candidate(dataset_id, "b", "root", "before")
    reloaded = await store.get_dataset(dataset_id)
    assert reloaded is not None
    reloaded_ids = {goal["id"]: goal for goal in reloaded["candidates"]}
    assert reloaded_ids["a"]["parent_candidate_id"] == "c"
    assert [
        goal["id"] for goal in reloaded["hierarchy"] if goal["parent_candidate_id"] is None
    ] == [
        "b",
        "root",
        "c",
    ]

    await store.save_result({**first, "run_id": str(uuid4()), "candidates": candidates()})
    rebuilt = await store.get_dataset(dataset_id)
    assert rebuilt is not None
    by_id = {goal["id"]: goal for goal in rebuilt["candidates"]}
    assert by_id["a"]["parent_candidate_id"] == "c"
    assert by_id["a"]["parent_override"] is True
    assert by_id["a"]["status"] == "confirmed"
    assert [goal["id"] for goal in rebuilt["hierarchy"] if goal["parent_candidate_id"] is None] == [
        "b",
        "root",
        "c",
    ]
    await engine.dispose()
