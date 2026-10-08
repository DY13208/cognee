"""Explicit canonical binding and proposal loop preview; no production access."""

import copy
from uuid import uuid4

import pytest

from cognee.modules.teleology.goal_orchestrated import compose_orchestrated_proposal
from cognee.modules.teleology.goal_patch import (
    compose_orchestrated_patch,
    submit_orchestrated_patch,
)
from cognee.modules.teleology.goal_store import MemoryGoalRunStore


def node(key, name, kind="goal"):
    return {
        "client_id": key,
        "name": name,
        "node_type": kind,
        "reason": "source supports node",
        "confidence": 0.8,
        "evidence_node_ids": ["doc"],
    }


def relation(source, target, kind, **extra):
    return {
        "source_client_id": source,
        "target_client_id": target,
        "relationship": kind,
        "reason": "business mechanism",
        "confidence": 0.8,
        "evidence_node_ids": ["doc"],
        **extra,
    }


def base():
    model, _ = compose_orchestrated_proposal(
        uuid4(), {"goals": [node("G2", "提升 UNOVE(UN) 项目盈利能力")]}, known_node_ids={"doc"}
    )
    # Production canonical ids can predate orchestrated deterministic ids.
    model["candidates"][0]["id"] = "existing-canonical-G2"
    return model


def patch(model, **extra):
    payload = {"submission_mode": "patch", "base_run_id": model["run_id"], **extra}
    return compose_orchestrated_patch(
        model["dataset_id"], payload, current=model, known_node_ids={"doc"}
    )


def test_candidate_id_binds_and_can_connect_new_nodes():
    model = base()
    before = copy.deepcopy(model)
    existing = model["candidates"][0]
    payload = node("G2", existing["name"])
    payload.update(candidate_id=existing["id"], reason="updated by stable id")
    edge = relation("P1", "", "serves")
    edge.pop("target_client_id")
    edge["target_candidate_id"] = existing["id"]
    result, summary = patch(
        model, upsert_goals=[payload, node("P1", "会员运营能力", "capability")], relations=[edge]
    )
    assert summary["valid"]
    assert model == before
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["id"] == existing["id"]
    assert result["candidates"][0]["reason"] == "updated by stable id"
    assert result["relations"][0]["target"] == existing["id"]
    assert summary["added_goal_ids"] == [result["candidates"][1]["id"]]


def test_same_name_without_candidate_id_is_explicit_error():
    model = base()
    result, summary = patch(model, upsert_goals=[node("G2", model["candidates"][0]["name"])])
    assert not summary["valid"]
    assert summary["critical_errors"][0]["reason"] == "EXISTING_CANDIDATE_BINDING_REQUIRED"
    assert result["candidates"] == model["candidates"]


@pytest.mark.parametrize("historical_status", ["legacy_confirmed", "confirmed"])
def test_current_canonical_priority_and_historical_cannot_be_bound(historical_status):
    model = base()
    old = {
        **model["candidates"][0],
        "id": "historical-G2",
        "status": historical_status,
        "outside_current_snapshot": True,
    }
    model["candidates"].insert(0, old)
    current = model["candidates"][1]
    result, summary = patch(
        model, upsert_goals=[{"candidate_id": current["id"], "reason": "current update"}]
    )
    assert summary["valid"]
    assert result["candidates"][0] == old
    assert result["candidates"][1]["reason"] == "current update"
    rejected, summary = patch(
        model, upsert_goals=[{"candidate_id": old["id"], "reason": "bad update"}]
    )
    assert not summary["valid"]
    assert summary["critical_errors"][0]["reason"] == "INVALID_EXISTING_CANDIDATE"
    assert rejected["candidates"] == model["candidates"]


@pytest.mark.parametrize(
    "fields",
    [
        {"source": "a", "target": "b"},
        {"source_id": "a", "target_id": "b"},
        {"source_ref": "a", "target_ref": "b"},
        {},
        {"source_client_id": "missing", "target_client_id": "b"},
        {"source_client_id": "a", "source_candidate_id": "bad", "target_client_id": "b"},
        {"source_candidate_id": "historical", "target_client_id": "b"},
    ],
)
def test_invalid_endpoint_never_becomes_self_loop(fields):
    payload = {
        "goals": [node("a", "提升收入"), node("b", "提升利润")],
        "relations": [
            {
                "relationship": "drives",
                "reason": "mechanism",
                "confidence": 0.8,
                "evidence_node_ids": ["doc"],
                **fields,
            }
        ],
    }
    model, summary = compose_orchestrated_proposal(uuid4(), payload, known_node_ids={"doc"})
    assert not summary["valid"]
    assert summary["critical_errors"][0]["reason"] == "INVALID_RELATION_ENDPOINT"
    assert model["relations"] == []
    assert summary["loop_preview"] == []


def un_v3_semantic_fixture():
    """Focused UN V3 regression, not a copy of the production 30-node snapshot."""
    return {
        "goals": [
            node("G2", "提升GMV规模"),
            node("G6", "提升采购履约"),
            node("G5", "提升渠道覆盖"),
            node("D1", "采购目标强度", "driver"),
            node("D2", "渠道扩张强度", "driver"),
            node("R2", "渠道扩张管理复杂度", "risk"),
            node("M1", "销售目标达成率", "metric"),
            node("C1", "全渠道控价体系", "constraint"),
            node("P1", "会员运营能力", "capability"),
        ],
        "relations": [
            relation("G2", "G6", "drives"),
            relation("G6", "G2", "advances"),
            relation("G2", "D1", "drives"),
            relation("D1", "G6", "sets"),
            relation("G5", "D2", "drives"),
            relation("D2", "R2", "amplifies"),
            relation("M1", "G2", "measures"),
            relation("C1", "G5", "constrains"),
            relation("P1", "G5", "enables"),
            relation("P1", "G2", "serves"),
        ],
    }


def test_un_v3_preview_one_reinforcing_loop_and_no_warnings():
    payload = un_v3_semantic_fixture()
    _, summary = compose_orchestrated_proposal(uuid4(), payload, known_node_ids={"doc"})
    assert summary["valid"]
    assert not summary["warnings"]
    assert len(summary["loop_preview"]) == 1
    loop = summary["loop_preview"][0]
    ids = summary["resolved_client_ids"]
    assert set(loop["nodes"]) == {ids["G2"], ids["G6"]}
    assert loop["loop_type"] == "Reinforcing"
    assert loop["negative_edge_count"] == 0
    assert loop["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_dry_run_patch_preview_connects_canonical_and_writes_nothing(monkeypatch):
    async def allow(*args, **kwargs):
        pass

    monkeypatch.setattr("cognee.modules.teleology.goal_patch._authorized_dataset", allow)
    model = base()
    store = MemoryGoalRunStore()
    await store.save_result(model)
    before = copy.deepcopy(store.runs)
    goal_id = model["candidates"][0]["id"]
    forward = relation("", "G6", "drives")
    forward.pop("source_client_id")
    forward["source_candidate_id"] = goal_id
    back = relation("G6", "", "advances", condition="demand remains stable")
    back.pop("target_client_id")
    back["target_candidate_id"] = goal_id
    summary = await submit_orchestrated_patch(
        model["dataset_id"],
        object(),
        {
            "base_run_id": model["run_id"],
            "dry_run": True,
            "upsert_goals": [node("G6", "提升采购履约")],
            "relations": [forward, back],
        },
        known_node_ids={"doc"},
        store=store,
    )
    assert summary["valid"]
    assert not summary["saved"]
    assert len(summary["loop_preview"]) == 1
    assert summary["loop_preview"][0]["status"] == "CONDITIONAL"
    assert summary["loop_preview"][0]["loop_type"] == "Reinforcing"
    assert store.runs == before


@pytest.mark.parametrize(
    "alias",
    [
        "source",
        "target",
        "source_id",
        "target_id",
        "source_ref",
        "target_ref",
        "sourceId",
        "targetRef",
    ],
)
def test_api_dto_keeps_unsupported_alias_for_explicit_endpoint_validation(alias):
    # Load the real DTO class declarations without initializing API services or databases.
    import ast
    import runpy
    from pathlib import Path
    from typing import Literal, Optional
    from uuid import UUID

    from pydantic import ConfigDict, Field

    from cognee.modules.teleology.goal_network import NodeType, Relationship

    root = Path(__file__).resolve().parents[5]
    tree = ast.parse(
        (root / "cognee/api/v1/teleology/routers/get_teleology_router.py").read_text(
            encoding="utf8"
        )
    )
    classes = [
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name.startswith("Orchestrated")
    ]
    namespace = {
        "__name__": __name__,
        "InDTO": runpy.run_path(str(root / "cognee/api/DTO.py"))["InDTO"],
        "List": list,
        "Literal": Literal,
        "Optional": Optional,
        "UUID": UUID,
        "Field": Field,
        "ConfigDict": ConfigDict,
        "NetworkNodeType": NodeType,
        "Relationship": Relationship,
    }
    exec(  # noqa: S102 - only the repository DTO class declarations are executed
        compile(ast.Module(body=classes, type_ignores=[]), "goal_network_api_dtos", "exec"),
        namespace,
    )
    payload = {
        "dataset_id": str(uuid4()),
        "submission_mode": "patch",
        "upsert_goals": [{"candidate_id": "canonical", "node_type": "driver"}],
        "relations": [
            {
                "source_candidate_id": "canonical",
                "target_client_id": "new",
                "relationship": "drives",
                "condition": False,
                alias: "invalid",
            }
        ],
    }
    parsed = namespace["OrchestratedGoalModelProposal"](**payload).model_dump(exclude_unset=True)
    assert parsed["upsert_goals"] == payload["upsert_goals"]
    assert "name" not in parsed["upsert_goals"][0]
    assert parsed["relations"][0] == payload["relations"][0]
    from cognee.modules.teleology.goal_orchestrated import (
        _relation_issue,
        resolve_relation_endpoints,
    )

    mapping = {"new": "new-id"}
    resolved = resolve_relation_endpoints(
        parsed["relations"], mapping, [{"id": "canonical"}, {"id": "new-id"}]
    )
    assert _relation_issue(resolved[0], mapping, "") == "INVALID_RELATION_ENDPOINT"


def test_historical_only_name_does_not_overwrite_retained_record():
    model = base()
    model["candidates"][0].update(status="legacy_confirmed", outside_current_snapshot=True)
    old = copy.deepcopy(model["candidates"][0])
    result, summary = patch(model, upsert_goals=[node("new", old["name"])])
    assert summary["valid"]
    assert result["candidates"][0] == old
    assert result["candidates"][1]["id"] != old["id"]
