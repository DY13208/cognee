"""Production goal build uses the LLM, persists proposals, and returns immediately."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from cognee.infrastructure.databases.relational import Base
from cognee.modules.teleology.goal_build import (
    build_tasks,
    load_dataset_sources,
    start_teleology_build,
)
from cognee.modules.teleology.goal_llm import GoalBuildLLM
from cognee.modules.teleology.goal_model_models import (
    TeleologyBuildRunRecord,
    TeleologyGoalCandidateRecord,
)
from cognee.modules.teleology.goal_store import (
    MemoryGoalRunStore,
    SqlGoalModelStore,
    use_goal_store,
)

ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(autouse=True)
def isolated_store():
    use_goal_store(MemoryGoalRunStore())
    yield
    use_goal_store(None)


def rich_sources() -> list[dict]:
    return [
        {
            "id": "resp",
            "name": "责任分工",
            "type": "Goal",
            "layer": "company_tree",
            "description": "职责目录",
            "note": "不是目标",
            "parent_name": "",
            "ancestor_names": [],
            "child_names": ["Arencia项目"],
            "related_documents": [],
            "related_entities": [],
            "graph_neighbors": [],
        },
        {
            "id": "project",
            "name": "Arencia项目",
            "type": "Goal",
            "layer": "company_tree",
            "description": "品牌项目",
            "note": "经营备注",
            "parent_name": "责任分工",
            "ancestor_names": ["责任分工", "经营树"],
            "child_names": ["项目利润分"],
            "related_documents": ["Arencia 利润说明"],
            "related_entities": ["Arencia"],
            "graph_neighbors": [{"name": "Arencia 利润说明", "type": "Document"}],
            "tree_parent_id": "resp",
        },
        {
            "id": "metric",
            "name": "项目利润分",
            "type": "Goal",
            "layer": "company_tree",
            "description": "利润指标",
            "note": "口径说明",
            "parent_name": "Arencia项目",
            "ancestor_names": ["Arencia项目", "责任分工"],
            "child_names": [],
            "related_documents": ["Arencia 利润说明"],
            "related_entities": ["Arencia"],
            "graph_neighbors": [],
            "tree_parent_id": "project",
        },
        {
            "id": "accuracy",
            "name": "Arencia利润核算准确性指标",
            "type": "Goal",
            "layer": "company_tree",
            "description": "核算准确性",
            "parent_name": "项目利润分",
            "ancestor_names": ["项目利润分", "Arencia项目"],
            "tree_parent_id": "metric",
        },
        {
            "id": "doc",
            "name": "Arencia 利润说明",
            "type": "Document",
            "layer": "document",
            "text": "Arencia 项目利润分口径",
            "description": "利润口径文档",
            "note": "文档证据",
        },
    ]


def _keyword_guards(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("keyword goal build was called")

    monkeypatch.setattr("cognee.modules.teleology.goal_model.classify_semantics", boom)
    monkeypatch.setattr("cognee.modules.teleology.goal_model.extract_candidates", boom)
    monkeypatch.setattr("cognee.modules.teleology.goal_model.build_hierarchy", boom)


async def _allow(*_args, **_kwargs):
    return object()


class _Gateway:
    def __init__(self, gate: asyncio.Event | None = None):
        self.calls: list[str] = []
        self.context: list[dict] = []
        self.gate = gate

    async def acreate_structured_output(self, text_input, system_prompt, response_model, **_kwargs):
        del system_prompt
        name = response_model.__name__
        self.calls.append(name)
        payload = json.loads(text_input)
        if name == "_ClassificationBatch":
            self.context = payload
            if self.gate is not None:
                await self.gate.wait()
            items = []
            for row in payload:
                semantic = {
                    "project": "Project",
                    "metric": "Metric",
                    "accuracy": "Metric",
                    "resp": "Responsibility",
                    "doc": "Document",
                }.get(row["id"], "Other")
                items.append(
                    {
                        "id": row["id"],
                        "semantic_class": semantic,
                        "classification_reason": "模型综合来源后判定。",
                    }
                )
            return response_model(items=items)
        if name == "_GoalBatch":
            if isinstance(payload, list) and payload and "confidence" in payload[0]:
                return response_model(goals=payload)
            return response_model(
                goals=[
                    {
                        "name": "提升 Arencia 项目盈利能力",
                        "description": "综合项目与利润分",
                        "reason": "项目和利润指标共同指向盈利结果",
                        "confidence": 0.82,
                        "source_node_ids": ["project", "metric"],
                        "evidence": [],
                    },
                    {
                        "name": "提高 Arencia 利润核算准确性",
                        "description": "综合准确性指标与说明",
                        "reason": "准确性指标与文档共同指向核算质量",
                        "confidence": 0.7,
                        "source_node_ids": ["accuracy", "doc"],
                        "evidence": [],
                    },
                    {
                        "name": "没有证据的目标",
                        "description": "空",
                        "reason": "没有来源",
                        "confidence": 0.9,
                        "source_node_ids": [],
                        "evidence": [],
                    },
                ]
            )
        if name == "_HierarchyBatch":
            profit = next(goal for goal in payload if "盈利" in goal["name"])
            accuracy = next(goal for goal in payload if "准确" in goal["name"])
            return response_model(
                links=[
                    {"id": profit["id"], "parent_candidate_id": "project"},
                    {"id": accuracy["id"], "parent_candidate_id": profit["id"]},
                ]
            )
        raise AssertionError(name)


def _install_gateway(monkeypatch, gateway: _Gateway):
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    async def available(self):
        del self
        return True

    monkeypatch.setattr(GoalBuildLLM, "available", available)
    monkeypatch.setattr(LLMGateway, "acreate_structured_output", gateway.acreate_structured_output)


async def _finished(view: dict):
    await build_tasks()[view["run_id"]]
    from cognee.modules.teleology.goal_store import get_goal_store

    return await get_goal_store().get_dataset(view["dataset_id"])


@pytest.mark.asyncio
async def test_production_build_calls_llm_gateway_and_keeps_evidence(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)
    gateway = _Gateway()
    _install_gateway(monkeypatch, gateway)
    dataset_id = uuid4()

    view = await start_teleology_build(dataset_id, object(), sources=rich_sources(), max_sources=20)
    saved = await _finished(view)
    project = next(row for row in gateway.context if row["id"] == "project")

    assert gateway.calls[0] == "_ClassificationBatch"
    assert "_GoalBatch" in gateway.calls
    assert "_HierarchyBatch" in gateway.calls
    assert project["description"] == "品牌项目"
    assert project["note"] == "经营备注"
    assert project["parent_name"] == "责任分工"
    assert project["ancestor_names"] == ["责任分工", "经营树"]
    assert project["child_names"] == ["项目利润分"]
    assert project["source_layer"] == "company_tree"
    assert project["related_documents"] == ["Arencia 利润说明"]
    assert project["related_entities"] == ["Arencia"]
    assert project["graph_neighbors"]
    names = [goal["name"] for goal in saved["candidates"]]
    assert "提升 Arencia 项目盈利能力" in names
    assert "Arencia项目" not in names
    assert "没有证据的目标" not in names
    profit = next(goal for goal in saved["candidates"] if "盈利" in goal["name"])
    accuracy = next(goal for goal in saved["candidates"] if "准确" in goal["name"])
    assert profit["parent_candidate_id"] is None
    assert accuracy["parent_candidate_id"] == profit["id"]
    assert profit["parent_candidate_id"] != "project"
    assert len(profit["evidence"]) >= 2
    assert set(profit["source_node_ids"]) == {"project", "metric"}
    assert saved["committed"] is False
    assert saved["graph_committed"] is False


@pytest.mark.asyncio
async def test_llm_unavailable_fails_without_keyword_fallback(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)

    async def unavailable(self):
        del self
        return False

    async def gateway(*_args, **_kwargs):
        raise AssertionError("gateway was called")

    monkeypatch.setattr(GoalBuildLLM, "available", unavailable)
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    monkeypatch.setattr(LLMGateway, "acreate_structured_output", gateway)
    view = await start_teleology_build(uuid4(), object(), sources=rich_sources())
    await build_tasks()[view["run_id"]]
    from cognee.modules.teleology.goal_store import get_goal_store

    status = await get_goal_store().get_run(view["run_id"])
    assert status["status"] == "failed"
    assert status["error_code"] == "llm_unavailable"
    assert await get_goal_store().get_dataset(view["dataset_id"]) is None


@pytest.mark.asyncio
async def test_gateway_error_fails_without_keyword_fallback(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)

    async def available(self):
        del self
        return True

    async def broken(*_args, **_kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(GoalBuildLLM, "available", available)
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    monkeypatch.setattr(LLMGateway, "acreate_structured_output", broken)
    view = await start_teleology_build(uuid4(), object(), sources=rich_sources())
    await build_tasks()[view["run_id"]]
    from cognee.modules.teleology.goal_store import get_goal_store

    status = await get_goal_store().get_run(view["run_id"])
    assert status["status"] == "failed"
    assert status["error_code"] == "llm_unavailable"


@pytest.mark.asyncio
async def test_post_returns_pending_and_background_finishes(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)
    gate = asyncio.Event()
    gateway = _Gateway(gate)
    _install_gateway(monkeypatch, gateway)
    started = asyncio.get_running_loop().time()
    view = await start_teleology_build(uuid4(), object(), sources=rich_sources())
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1
    assert view["status"] == "pending"
    assert view["run_id"]
    assert view["committed"] is False
    from cognee.modules.teleology.goal_store import get_goal_store

    waiting = await get_goal_store().get_run(view["run_id"])
    assert waiting["status"] in {"pending", "running"}
    gate.set()
    saved = await _finished(view)
    assert saved["status"] == "completed"
    assert saved["candidates"]


@pytest.mark.asyncio
async def test_client_cancel_does_not_cancel_the_build(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)
    gate = asyncio.Event()
    entered = asyncio.Event()
    gateway = _Gateway(gate)

    async def acreate_structured_output(text_input, system_prompt, response_model, **kwargs):
        if response_model.__name__ == "_ClassificationBatch":
            entered.set()
        return await _Gateway.acreate_structured_output(
            gateway, text_input, system_prompt, response_model, **kwargs
        )

    gateway.acreate_structured_output = acreate_structured_output
    _install_gateway(monkeypatch, gateway)
    box: dict = {}

    async def client():
        box["view"] = await start_teleology_build(uuid4(), object(), sources=rich_sources())
        await asyncio.sleep(30)

    client_task = asyncio.create_task(client())
    await asyncio.wait_for(entered.wait(), timeout=2)
    client_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await client_task
    run_id = box["view"]["run_id"]
    assert not build_tasks()[run_id].done()
    gate.set()
    await build_tasks()[run_id]
    from cognee.modules.teleology.goal_store import get_goal_store

    status = await get_goal_store().get_run(run_id)
    assert status["status"] == "completed"
    assert status["canonical_goal_count"] >= 1


@pytest.mark.asyncio
async def test_goal_model_survives_a_new_store_and_keeps_review(monkeypatch):
    _keyword_guards(monkeypatch)
    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", _allow)
    gateway = _Gateway()
    _install_gateway(monkeypatch, gateway)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [TeleologyBuildRunRecord.__table__, TeleologyGoalCandidateRecord.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlGoalModelStore(factory)
    use_goal_store(store)
    dataset_id = uuid4()
    try:
        view = await start_teleology_build(dataset_id, object(), sources=rich_sources())
        await build_tasks()[view["run_id"]]
        first = await store.get_dataset(dataset_id)
        profit = next(goal for goal in first["candidates"] if "盈利" in goal["name"])
        await store.set_candidate_status(dataset_id, profit["id"], "confirmed")
        purpose = first["purposes"][0]
        await store.set_teleology_status(dataset_id, purpose["id"], "confirmed", "purpose")
        async with factory() as session:
            run = await session.get(TeleologyBuildRunRecord, UUID(view["run_id"]))
            row = await session.get(TeleologyGoalCandidateRecord, profit["id"])
        assert run is not None
        assert run.committed == 0
        assert run.status == "completed"
        assert row is not None
        assert row.status == "confirmed"
        assert row.parent_candidate_id is None
        assert json.loads(row.evidence)
        assert json.loads(row.source_node_ids) == ["project", "metric"]

        use_goal_store(None)
        restarted = SqlGoalModelStore(factory)
        use_goal_store(restarted)
        loaded = await restarted.get_dataset(dataset_id)
        reviewed = next(goal for goal in loaded["candidates"] if goal["id"] == profit["id"])
        assert reviewed["status"] == "confirmed"
        assert (
            next(item["status"] for item in loaded["purposes"] if item["id"] == purpose["id"])
            == "confirmed"
        )
        assert reviewed["evidence"]
        assert loaded["graph_committed"] is False
        status = await restarted.get_run(view["run_id"])
        assert status["status"] == "completed"
        assert status["stage"]
        assert "processed_sources" in status
        assert "progress" in status
        assert "stage_stats" in status
    finally:
        use_goal_store(None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_loading_sources_does_not_write_the_company_tree(monkeypatch):
    queries: list[str] = []

    class Graph:
        async def query(self, cypher, _params=None):
            queries.append(cypher)
            compact = " ".join(cypher.split())
            if "RETURN m.name" in compact:
                return [("利润说明", "Document", "mentions")]
            if "RETURN c.name" in compact:
                return [("项目利润分",)]
            if "RETURN n.name" in compact and "RETURN n.id" not in compact:
                return [("经营树",)]
            if compact.startswith("MATCH (n:Node)"):
                if _params and _params.get("offset"):
                    return []
                return [
                    (
                        "project",
                        "Arencia项目",
                        "Goal",
                        {"description": "品牌项目", "source_note": "经营备注"},
                    )
                ]
            return []

    class Dataset:
        owner_id = uuid4()

    @asynccontextmanager
    async def context(*_args, **_kwargs):
        yield None

    async def dataset(*_args, **_kwargs):
        return Dataset()

    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", dataset)
    monkeypatch.setattr(
        "cognee.modules.teleology.goal_build.get_graph_engine", lambda: _async_graph(Graph())
    )
    monkeypatch.setattr(
        "cognee.modules.teleology.goal_build.set_database_global_context_variables", context
    )
    sources = await load_dataset_sources(uuid4(), object(), batch_size=20, max_sources=20)
    project = next(source for source in sources if source["id"] == "project")

    assert queries
    assert all(query.strip().upper().startswith("MATCH") for query in queries)
    assert project["description"] == "品牌项目"
    assert project["note"] == "经营备注"
    assert "项目利润分" in project["child_names"]
    assert project["related_documents"]
    build = (ROOT / "cognee" / "modules" / "teleology" / "goal_build.py").read_text(
        encoding="utf-8"
    )
    model = (ROOT / "cognee" / "modules" / "teleology" / "goal_model.py").read_text(
        encoding="utf-8"
    )
    assert "classify_semantics" not in build
    assert "extract_candidates" not in build
    assert "run_goal_build(" not in build
    assert "has_subgoal" not in model
    assert "commit_teleology_proposal" not in build


async def _async_graph(graph):
    return graph
