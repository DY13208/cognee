"""WorkBuddy submits an analyzed goal model. Cognee only validates and stores it."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cognee.modules.teleology.goal_model import STORE, GoalBuildError, candidate_id
from cognee.modules.teleology.goal_orchestrated import (
    compose_orchestrated_proposal,
    submit_orchestrated_goal_model,
)
from cognee.modules.teleology.goal_store import MemoryGoalRunStore, use_goal_store

NODES = {
    "arencia": "Arencia项目",
    "profit": "项目利润分",
    "repurchase": "会员复购",
    "turnover": "库存周转",
    "health": "库存健康度",
}
KNOWN = set(NODES)


def _evidence(node_id: str, semantic: str = "Metric") -> dict:
    return {
        "node_id": node_id,
        "name": NODES.get(node_id, node_id),
        "source_layer": "company_tree",
        "semantic_class": semantic,
        "text": NODES.get(node_id, node_id),
        "reason": "该节点支持这个目标",
    }


def _goal(client_id: str, name: str, node_ids: list[str], **overrides) -> dict:
    semantic = overrides.pop("semantic", "Metric")
    evidence = overrides.pop("evidence", [_evidence(node_id, semantic) for node_id in node_ids])
    row = {
        "client_id": client_id,
        "name": name,
        "description": name,
        "reason": "由证据归纳出的业务结果",
        "confidence": 0.86,
        "source_node_ids": list(node_ids),
        "evidence": evidence,
    }
    row.update(overrides)
    return row


def _link(parent: str, child: str, nodes: list[str] | None = None, **overrides) -> dict:
    row = {
        "parent_client_id": parent,
        "child_client_id": child,
        "reason": "该目标是上级业务结果的更具体实现结果",
        "confidence": 0.82,
        "evidence_node_ids": nodes or ["repurchase"],
    }
    row.update(overrides)
    return row


def _sample() -> dict:
    return {
        "generated_by": "workbuddy_orchestrated",
        "goals": [
            _goal("g1", "提升公司整体经营利润", ["repurchase"], semantic="GoalSignal"),
            _goal(
                "g2",
                "提升 Arencia 项目盈利能力",
                ["arencia", "profit"],
                evidence=[_evidence("arencia", "Project"), _evidence("profit", "Metric")],
            ),
            _goal("g3", "提升库存周转健康度与资金效率", ["turnover", "health"]),
        ],
        "hierarchy": [_link("g1", "g2"), _link("g1", "g3", ["turnover"])],
        "purposes": [],
        "constraints": [],
        "relations": [],
    }


def _compose(payload: dict, previous: list | None = None, teleology: dict | None = None):
    return compose_orchestrated_proposal(
        uuid4(),
        payload,
        known_node_ids=KNOWN,
        previous=previous,
        previous_teleology=teleology,
    )


@pytest.fixture
def memory_store(monkeypatch):
    store = MemoryGoalRunStore()
    use_goal_store(store)

    async def allow(*_args, **_kwargs):
        return SimpleNamespace(owner_id="owner")

    monkeypatch.setattr(
        "cognee.modules.teleology.goal_orchestrated._authorized_dataset",
        allow,
    )
    yield store
    use_goal_store(None)
    STORE.clear()


def test_legal_proposal_creates_three_proposed_goals():
    dataset_id = uuid4()
    model, summary = compose_orchestrated_proposal(dataset_id, _sample(), known_node_ids=KNOWN)

    names = {goal["name"] for goal in model["candidates"]}
    assert names == {
        "提升公司整体经营利润",
        "提升 Arencia 项目盈利能力",
        "提升库存周转健康度与资金效率",
    }
    assert summary["accepted"]["goals"] == 3
    assert summary["accepted"]["hierarchy"] == 2
    assert summary["status"] == "completed"
    assert summary["mode"] == "orchestrated"
    by_client = {}
    for goal in model["candidates"]:
        assert goal["status"] == "proposed"
        assert goal["id"] != goal.get("client_id")
        assert goal["id"] == candidate_id(dataset_id, goal["name"])
        assert goal["generated_by"] == "workbuddy_orchestrated"
        by_client[goal["name"]] = goal
    child = by_client["提升 Arencia 项目盈利能力"]
    parent = by_client["提升公司整体经营利润"]
    assert child["parent_candidate_id"] == parent["id"]
    assert NODES["arencia"] not in names
    assert NODES["profit"] not in names


def test_goal_without_evidence_is_rejected_and_the_batch_continues():
    payload = _sample()
    payload["goals"].append(
        _goal("g4", "提升会员复购贡献", ["repurchase"], evidence=[], source_node_ids=["repurchase"])
    )
    model, summary = _compose(payload)

    assert summary["rejected"]["goals"] == 1
    assert summary["issues"][-1]["reason"] == "missing_evidence"
    assert summary["accepted"]["goals"] == 3
    assert len(model["candidates"]) == 3


def test_missing_source_node_marks_evidence_invalid():
    payload = _sample()
    payload["goals"].append(_goal("g7", "提升未知节点对应的结果", ["missing-node"]))
    _model, summary = _compose(payload)

    assert summary["rejected"]["goals"] == 1
    assert summary["issues"][-1] == {
        "kind": "goal",
        "client_id": "g7",
        "reason": "invalid_evidence",
    }
    assert summary["accepted"]["goals"] == 3


def test_responsibility_is_not_accepted_as_a_goal():
    payload = _sample()
    payload["goals"].append(_goal("duty", "责任分工", ["repurchase"], semantic="Responsibility"))
    model, summary = _compose(payload)

    assert summary["issues"][-1]["reason"] == "responsibility_not_goal"
    assert "责任分工" not in {goal["name"] for goal in model["candidates"]}


def test_metric_only_name_is_rejected_and_outcome_metric_text_is_kept():
    payload = _sample()
    payload["goals"].append(_goal("metric", "项目利润分", ["profit"]))
    model, summary = _compose(payload)

    assert any(issue["reason"] == "metric_only" for issue in summary["issues"])
    names = {goal["name"] for goal in model["candidates"]}
    assert "项目利润分" not in names
    assert "提升库存周转健康度与资金效率" in names


def test_duplicate_goal_is_not_created_again():
    payload = {
        "goals": [
            _goal(
                "a",
                "提升 Arencia 项目盈利能力",
                ["arencia", "profit"],
                evidence=[_evidence("arencia", "Project"), _evidence("profit", "Metric")],
            ),
            _goal(
                "b",
                "提高 Arencia 项目利润表现",
                ["arencia", "profit"],
                evidence=[_evidence("arencia", "Project"), _evidence("profit", "Metric")],
            ),
            _goal("c", "改善 Arencia 盈利能力", ["repurchase"], semantic="GoalSignal"),
        ]
    }
    model, summary = _compose(payload)
    issue = next(item for item in summary["issues"] if item["client_id"] == "b")

    assert summary["accepted"]["goals"] == 1
    assert summary["duplicates"] == 2
    assert len(model["candidates"]) == 1
    assert issue["reason"] == "duplicate"
    assert issue["duplicate_of"] == model["candidates"][0]["id"]
    assert issue["existing_candidate_id"] == model["candidates"][0]["id"]


def test_duplicate_goal_merges_new_evidence():
    payload = {
        "goals": [
            _goal(
                "a",
                "提升 Arencia 项目盈利能力",
                ["arencia", "profit"],
                evidence=[_evidence("arencia", "Project"), _evidence("profit", "Metric")],
            ),
            _goal("c", "改善 Arencia 盈利能力", ["repurchase"], semantic="GoalSignal"),
        ]
    }
    model, summary = _compose(payload)

    assert summary["duplicates"] == 1
    assert {entry["node_id"] for entry in model["candidates"][0]["evidence"]} >= {
        "arencia",
        "profit",
        "repurchase",
    }


def test_hierarchy_self_loop_is_rejected():
    payload = _sample()
    payload["hierarchy"] = [_link("g1", "g1")]
    model, summary = _compose(payload)
    parent = next(goal for goal in model["candidates"] if goal["name"].startswith("提升公司"))

    assert summary["rejected"]["hierarchy"] == 1
    assert summary["issues"][-1]["reason"] == "self_parent"
    assert parent["parent_candidate_id"] in (None, "")


def test_hierarchy_cycle_is_rejected():
    payload = _sample()
    payload["hierarchy"] = [_link("g1", "g2"), _link("g2", "g1")]
    model, summary = _compose(payload)

    assert summary["rejected"]["hierarchy"] == 1
    assert summary["issues"][-1]["reason"] == "cycle"
    parents = {
        goal["id"]: goal.get("parent_candidate_id")
        for goal in model["candidates"]
        if goal.get("parent_candidate_id")
    }
    for child, parent in list(parents.items()):
        seen = {child}
        cursor = parent
        while cursor:
            assert cursor not in seen
            seen.add(cursor)
            cursor = parents.get(cursor)


def test_hierarchy_multiple_parents_reject_only_the_extra_edge():
    payload = _sample()
    payload["hierarchy"] = [_link("g1", "g2"), _link("g3", "g2", ["turnover"])]
    model, summary = _compose(payload)
    child = next(goal for goal in model["candidates"] if "Arencia" in goal["name"])
    first = next(goal for goal in model["candidates"] if goal["name"].startswith("提升公司"))

    assert summary["accepted"]["hierarchy"] == 1
    assert summary["rejected"]["hierarchy"] == 1
    assert summary["issues"][-1]["reason"] == "multiple_parents"
    assert child["parent_candidate_id"] == first["id"]


def test_relation_self_loop_is_rejected():
    payload = _sample()
    payload["relations"] = [
        {
            "source_client_id": "g1",
            "target_client_id": "g1",
            "relationship": "serves",
            "reason": "自己服务自己",
            "confidence": 0.4,
            "source_node_ids": ["repurchase"],
            "evidence": [_evidence("repurchase", "GoalSignal")],
        }
    ]
    model, summary = _compose(payload)

    assert summary["rejected"]["relations"] == 1
    assert summary["issues"][-1]["reason"] == "self_loop"
    assert model["relations"] == []


def test_relation_without_evidence_is_rejected():
    payload = _sample()
    payload["relations"] = [
        {
            "source_client_id": "g2",
            "target_client_id": "g1",
            "relationship": "advances",
            "reason": "没有证据",
            "confidence": 0.7,
            "source_node_ids": [],
            "evidence": [],
        }
    ]
    _model, summary = _compose(payload)

    assert summary["rejected"]["relations"] == 1
    assert summary["issues"][-1]["reason"] == "missing_evidence"


def test_hierarchy_does_not_become_an_advances_relation():
    model, summary = _compose(_sample())

    assert summary["accepted"]["hierarchy"] == 2
    assert summary["accepted"]["relations"] == 0
    assert model["relations"] == []
    assert model["teleology"]["relations"] == []


def test_structural_has_subgoal_copy_is_not_a_hierarchy_edge():
    payload = _sample()
    payload["hierarchy"] = [_link("g1", "g2", relationship="has_subgoal")]
    model, summary = _compose(payload)

    assert summary["rejected"]["hierarchy"] == 1
    assert summary["issues"][-1]["reason"] == "structural_copy"
    assert model["relations"] == []


def test_constraint_does_not_enter_the_goal_tree():
    payload = _sample()
    payload["constraints"] = [
        {
            "client_id": "c1",
            "goal_client_id": "g2",
            "name": "达播费比不得超过40%",
            "reason": "费用边界来自项目约束",
            "confidence": 0.9,
            "source_node_ids": ["profit"],
            "evidence": [_evidence("profit", "Constraint")],
        }
    ]
    payload["goals"].append(_goal("bad", "达播费比不得超过40%", ["profit"]))
    model, summary = _compose(payload)
    names = {goal["name"] for goal in model["candidates"]}
    hierarchy_names = {
        goal["name"] for goal in model["candidates"] if goal.get("status") != "rejected"
    }

    assert "达播费比不得超过40%" not in names
    assert "达播费比不得超过40%" not in hierarchy_names
    assert summary["accepted"]["constraints"] == 1
    assert model["constraints"][0]["kind"] == "constraint"
    assert model["constraints"][0]["status"] == "proposed"
    assert any(issue["reason"] == "constraint_not_goal" for issue in summary["issues"])


def test_purpose_must_bind_an_accepted_goal():
    payload = _sample()
    payload["purposes"] = [
        {
            "goal_client_id": "missing",
            "name": "没有目标的目的",
            "reason": "无法挂接",
            "confidence": 0.5,
            "source_node_ids": ["repurchase"],
            "evidence": [_evidence("repurchase", "GoalSignal")],
        },
        {
            "goal_client_id": "g1",
            "name": "提升品牌项目组合的整体利润贡献",
            "reason": "公司利润是这些项目结果的目的",
            "confidence": 0.8,
            "source_node_ids": ["repurchase"],
            "evidence": [_evidence("repurchase", "GoalSignal")],
        },
    ]
    model, summary = _compose(payload)

    assert summary["rejected"]["purposes"] == 1
    assert summary["issues"][0]["reason"] == "missing_goal" or any(
        issue["reason"] == "missing_goal" for issue in summary["issues"]
    )
    assert summary["accepted"]["purposes"] == 1
    assert model["purposes"][0]["goal_id"]
    assert model["purposes"][0]["status"] == "proposed"


def test_empty_goals_reject_the_request():
    with pytest.raises(GoalBuildError):
        _compose({"goals": []})


@pytest.mark.asyncio
async def test_orchestrated_run_and_candidates_persist(memory_store):
    dataset_id = uuid4()
    summary = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        _sample(),
        known_node_ids=KNOWN,
        store=memory_store,
    )
    view = await memory_store.get_dataset(dataset_id)
    stored = memory_store.runs[summary["run_id"]]

    assert stored["mode"] == "orchestrated"
    assert stored["status"] == "completed"
    assert stored["payload"]["generated_by"] == "workbuddy_orchestrated"
    assert view is not None
    assert {goal["name"] for goal in view["candidates"]} == {
        "提升公司整体经营利润",
        "提升 Arencia 项目盈利能力",
        "提升库存周转健康度与资金效率",
    }
    assert all(goal["status"] == "proposed" for goal in view["candidates"])
    assert view["committed"] is False
    assert view["graph_committed"] is False


@pytest.mark.asyncio
async def test_reloaded_store_still_reads_the_proposal():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from cognee.modules.teleology.goal_model_models import (
        TeleologyBuildRunRecord,
        TeleologyGoalCandidateRecord,
    )
    from cognee.modules.teleology.goal_store import SqlGoalModelStore

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    def _create(sync_conn):
        TeleologyBuildRunRecord.__table__.create(sync_conn)
        TeleologyGoalCandidateRecord.__table__.create(sync_conn)

    async with engine.begin() as connection:
        await connection.run_sync(_create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    dataset_id = uuid4()
    first = SqlGoalModelStore(sessions)
    model, summary = compose_orchestrated_proposal(dataset_id, _sample(), known_node_ids=KNOWN)
    await first.save_result(model)
    second = SqlGoalModelStore(sessions)
    view = await second.get_dataset(dataset_id)

    assert view is not None
    assert view["run_id"] == summary["run_id"]
    assert view["mode"] == "orchestrated"
    assert len(view["candidates"]) == 3
    assert view["committed"] is False
    assert view["graph_committed"] is False
    await engine.dispose()


def test_response_is_not_committed():
    _model, summary = _compose(_sample())

    assert summary["committed"] is False
    assert summary["graph_committed"] is False


@pytest.mark.asyncio
async def test_company_tree_is_not_written(memory_store, monkeypatch):
    calls = []

    class Graph:
        async def query(self, text, params):
            calls.append(("query", text))
            return [[node_id] for node_id in params["ids"] if node_id in KNOWN]

        def __getattr__(self, name):
            async def forbidden(*_args, **_kwargs):
                calls.append((name, "write"))
                raise AssertionError(name)

            return forbidden

    async def engine():
        return Graph()

    @asynccontextmanager
    async def scope(*_args, **_kwargs):
        yield None

    monkeypatch.setattr("cognee.modules.teleology.goal_orchestrated.get_graph_engine", engine)
    monkeypatch.setattr(
        "cognee.modules.teleology.goal_orchestrated.set_database_global_context_variables",
        scope,
    )
    dataset_id = uuid4()
    summary = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        _sample(),
        store=memory_store,
    )
    view = await memory_store.get_dataset(dataset_id)

    assert calls
    assert {name for name, *_rest in calls} == {"query"}
    assert summary["committed"] is False
    assert summary["graph_committed"] is False
    assert view["graph_committed"] is False
    assert "Arencia项目" not in {goal["name"] for goal in view["candidates"]}
    assert "责任分工" not in {goal["name"] for goal in view["candidates"]}
