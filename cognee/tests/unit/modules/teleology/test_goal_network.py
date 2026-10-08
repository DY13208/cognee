"""Frozen Enterprise Goal Network semantics without production data access."""

import copy
import json
from uuid import uuid4

import pytest

from cognee.modules.teleology.goal_network import (
    NODE_TYPES,
    RELATIONS,
    analyze_feedback_loops,
    semantic_warnings,
)
from cognee.modules.teleology.goal_orchestrated import compose_orchestrated_proposal
from cognee.modules.teleology.goal_patch import compose_orchestrated_patch
from cognee.modules.teleology.goal_store import MemoryGoalRunStore, dataset_view


def proposal(relationship="drives", node_type="driver"):
    return {
        "goals": [
            {
                "client_id": key,
                "name": name,
                "node_type": kind,
                "reason": "evidence",
                "confidence": 0.8,
                "evidence_node_ids": ["doc"],
            }
            for key, name, kind in [("a", "采购目标强度", node_type), ("b", "提升经营结果", "goal")]
        ],
        "relations": [
            {
                "source_client_id": "a",
                "target_client_id": "b",
                "relationship": relationship,
                "reason": "mechanism",
                "confidence": 0.7,
                "evidence_node_ids": ["doc"],
                "condition": {"expression": "growth > demand", "status": "unresolved"},
            }
        ],
    }


def compose(payload):
    return compose_orchestrated_proposal(uuid4(), payload, known_node_ids={"doc"})


@pytest.mark.parametrize("relationship", sorted(RELATIONS))
@pytest.mark.asyncio
async def test_snapshot_round_trip(relationship):
    model, summary = compose(proposal(relationship))
    assert summary["valid"]
    store = MemoryGoalRunStore()
    await store.save_result(json.loads(json.dumps(model)))
    result = await store.get_dataset(model["dataset_id"])
    assert result["relations"] == model["relations"]
    assert result["candidates"][0]["node_type"] == "driver"
    assert result["relations"][0]["condition"]["status"] == "unresolved"
    assert result["relations"][0]["evidence_node_ids"] == ["doc"]


@pytest.mark.parametrize("kind", sorted(NODE_TYPES))
def test_node_types(kind):
    payload = proposal(node_type=kind)
    payload["goals"][0]["name"] = "提升业务能力" if kind == "goal" else "业务变量"
    model, summary = compose(payload)
    assert summary["valid"]
    assert model["candidates"][0]["node_type"] == kind


@pytest.mark.parametrize(
    "kind,relationship,warn",
    [
        ("metric", "advances", True),
        ("constraint", "advances", True),
        ("metric", "measures", False),
        ("constraint", "constrains", False),
        ("driver", "sets", False),
        ("driver", "amplifies", False),
        ("risk", "blocks", False),
        ("capability", "enables", False),
    ],
)
def test_semantics(kind, relationship, warn):
    model, summary = compose(proposal(relationship, kind))
    assert summary["valid"]
    assert bool(semantic_warnings(model["candidates"], model["relations"])) == warn
    assert bool(summary["warnings"]) == warn


def edge(source, target, relationship, **extras):
    return {
        "source_id": source,
        "target_id": target,
        "relationship": relationship,
        "confidence": 0.8,
        "evidence_node_ids": ["doc"],
        **extras,
    }


@pytest.mark.parametrize(
    "relation", ["serves", "enables", "constrains", "measures", "sets", "has_subgoal"]
)
def test_noncausal_never_closes_loop(relation):
    assert analyze_feedback_loops([edge("a", "b", "drives"), edge("b", "a", relation)]) == []


@pytest.mark.parametrize(
    "relations,kind,count",
    [
        (["drives", "amplifies"], "Reinforcing", 0),
        (["advances", "blocks"], "Balancing", 1),
        (["blocks", "blocks"], "Reinforcing", 2),
    ],
)
def test_loop_polarity(relations, kind, count):
    loops = analyze_feedback_loops([edge("a", "b", relations[0]), edge("b", "a", relations[1])])
    assert len(loops) == 1
    assert loops[0]["loop_type"] == kind
    assert loops[0]["negative_edge_count"] == count
    assert loops[0]["status"] == "ACTIVE"


@pytest.mark.parametrize(
    "condition,status",
    [
        (False, None),
        ({"status": "inactive"}, None),
        ("growth > demand", "CONDITIONAL"),
        ({"status": "unresolved"}, "CONDITIONAL"),
        (True, "ACTIVE"),
        ({"status": "active"}, "ACTIVE"),
    ],
)
def test_condition_activation(condition, status):
    loops = analyze_feedback_loops(
        [edge("a", "b", "amplifies", condition=condition), edge("b", "a", "blocks")]
    )
    if status is None:
        assert not loops
    else:
        assert loops[0]["status"] == status
        assert loops[0]["conditions"] == [condition]


def test_patch_preserves_condition_and_type():
    model, _ = compose(proposal())
    payload = proposal("sets", "driver")
    payload["upsert_goals"] = payload.pop("goals")
    for raw, stored in zip(payload["upsert_goals"], model["candidates"]):
        raw["candidate_id"] = stored["id"]
    payload.update(submission_mode="patch", base_run_id=model["run_id"])
    patched, summary = compose_orchestrated_patch(
        model["dataset_id"],
        payload,
        known_node_ids={"doc"},
        current=model,
    )
    assert summary["valid"]
    assert patched["candidates"][0]["node_type"] == "driver"
    assert patched["relations"][-1]["condition"] == payload["relations"][0]["condition"]


def test_old_snapshot_view_is_unchanged_and_not_mutated():
    old = {
        "id": "f7d609ae-4e88-4e4f-b8b3-523e92246bd4",
        "dataset_id": "test",
        "payload": {
            "candidates": [{"id": "a", "name": "old", "status": "confirmed"}],
            "relations": [edge("a", "b", r) for r in ["advances", "serves", "blocks"]],
        },
    }
    before = copy.deepcopy(old)
    result = dataset_view(old, old["payload"]["candidates"])
    assert old == before
    assert result["relations"] == old["payload"]["relations"]
    assert result["candidates"] == old["payload"]["candidates"]
    assert "node_type" not in result["candidates"][0]


def test_loop_excludes_retired_nodes_and_structural_edges():
    relations = [edge("a", "b", "advances"), edge("b", "a", "drives")]
    assert not analyze_feedback_loops(
        relations, nodes=[{"id": "a"}, {"id": "b", "outside_current_snapshot": True}]
    )
    relations[0]["retrieval_only"] = True
    assert not analyze_feedback_loops(relations)


@pytest.mark.parametrize("relationship", sorted(RELATIONS))
@pytest.mark.asyncio
async def test_sql_snapshot_round_trip(relationship):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from cognee.modules.teleology.goal_model_models import (
        TeleologyBuildRunRecord,
        TeleologyGoalCandidateRecord,
    )
    from cognee.modules.teleology.goal_store import SqlGoalModelStore

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TeleologyBuildRunRecord.__table__.create)
            await connection.run_sync(TeleologyGoalCandidateRecord.__table__.create)
        store = SqlGoalModelStore(async_sessionmaker(engine, expire_on_commit=False))
        model, _ = compose(proposal(relationship))
        await store.save_result(model)
        view = await store.get_dataset(model["dataset_id"])
        assert view["relations"] == model["relations"]
        assert view["candidates"][0]["node_type"] == "driver"
        assert view["candidates"][0]["evidence_node_ids"] == ["doc"]
        history = await store.list_runs(model["dataset_id"])
        assert history[0]["run_id"] == model["run_id"]
    finally:
        await engine.dispose()


def test_patch_omitted_condition_and_type_remain_intact():
    model, _ = compose(proposal())
    payload = proposal()
    payload["upsert_goals"] = payload.pop("goals")
    for raw, stored in zip(payload["upsert_goals"], model["candidates"]):
        raw["candidate_id"] = stored["id"]
    payload["upsert_goals"][0].pop("node_type")
    payload["relations"][0].pop("condition")
    payload.update(submission_mode="patch", base_run_id=model["run_id"])
    patched, summary = compose_orchestrated_patch(
        model["dataset_id"],
        payload,
        known_node_ids={"doc"},
        current=model,
    )
    assert summary["valid"]
    assert patched["candidates"][0]["node_type"] == "driver"
    assert patched["relations"][0]["condition"] == model["relations"][0]["condition"]


@pytest.mark.parametrize("condition", [42, {"status": "unknown"}, {"status": []}])
def test_invalid_condition_is_a_validation_error(condition):
    payload = proposal()
    payload["relations"][0]["condition"] = condition
    _, summary = compose(payload)
    assert not summary["valid"]
    assert summary["critical_errors"][0]["reason"] == "invalid_condition"
