"""Additional parent aliases, invalid endpoints, and isolated SQL persistence."""

import copy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cognee.api.v1.teleology.routers.get_teleology_router import OrchestratedHierarchyIn
from cognee.modules.teleology.goal_model_models import (
    TeleologyBuildRunRecord,
    TeleologyGoalCandidateRecord,
)
from cognee.modules.teleology.goal_store import SqlGoalModelStore
from cognee.tests.unit.modules.teleology.test_goal_patch_parent_contract import (
    baseline,
    candidate,
    submit,
)

pytest_plugins = ("cognee.tests.unit.modules.teleology.test_goal_patch_parent_contract",)


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["self", "foreign", "missing", "historical", "conflicting"])
async def test_invalid_parent_endpoints_reject_without_save(isolated_store, parent):
    dataset_id, view, ids = await baseline(isolated_store)
    value = ids["child"] if parent == "self" else str(uuid4())
    if parent == "foreign":
        _, _, foreign = await baseline(isolated_store)
        value = foreign["new"]
    if parent == "historical":
        old = {
            **candidate(view, ids["new"]),
            "id": value,
            "status": "legacy_confirmed",
            "outside_current_snapshot": True,
        }
        isolated_store.runs[view["current_run_id"]]["candidates"].append(old)
    upsert = {"candidate_id": ids["child"], "parent_candidate_id": value}
    if parent == "conflicting":
        upsert.update(parent_candidate_id=ids["new"], parent_id=ids["old"])
    before = copy.deepcopy(isolated_store.runs)
    result = await submit(isolated_store, dataset_id, view, upsert_goals=[upsert])
    assert not result["valid"] and not result["saved"]
    assert result["critical_errors"] and result["rejected"]["hierarchy"] == 1
    assert isolated_store.runs == before


@pytest.mark.asyncio
async def test_parent_alias_preserves_all_other_fields_and_relations(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    original = copy.deepcopy(candidate(view, ids["child"]))
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[
            {
                "candidate_id": ids["child"],
                "name": original["name"],
                "parent_id": ids["new"],
            }
        ],
    )
    assert result["saved"]
    after = await isolated_store.get_dataset(dataset_id)
    child = candidate(after, ids["child"])
    for key in ("id", "name", "node_type", "evidence", "source_node_ids", "evidence_node_ids"):
        assert child.get(key) == original.get(key)
    assert child["parent_candidate_id"] == ids["new"]
    assert after["relations"] == view["relations"]


def test_unknown_hierarchy_fields_are_explicitly_rejected():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        OrchestratedHierarchyIn.model_validate({"child_ref": "x", "parent_ref": "y"})


@pytest.mark.asyncio
async def test_sql_reparent_overrides_manual_parent_and_preserves_history(isolated_store):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TeleologyBuildRunRecord.__table__.create)
            await connection.run_sync(TeleologyGoalCandidateRecord.__table__.create)
        store = SqlGoalModelStore(async_sessionmaker(engine, expire_on_commit=False))
        dataset_id, view, ids = await baseline(store)
        await store.move_candidate(dataset_id, ids["child"], ids["old"], "inside")
        original_run = await store.get_run(view["current_run_id"])
        result = await submit(
            store,
            dataset_id,
            view,
            upsert_goals=[
                {
                    "candidate_id": ids["child"],
                    "parent_candidate_id": ids["new"],
                }
            ],
        )
        assert result["saved"] and result["valid"]
        after = await store.get_dataset(dataset_id)
        assert candidate(after, ids["child"])["parent_candidate_id"] == ids["new"]
        assert await store.get_run(view["current_run_id"]) == original_run
    finally:
        await engine.dispose()
